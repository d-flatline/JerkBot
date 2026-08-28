#!/usr/bin/env python3
"""
jerkcity_bot.py

Terminal-only IRC bot that ports every feature of the "Jerkcity IRC
Bot" Android app into a single Python script. No GUI here — every
option that was a field/switch/slider in the app is instead a
variable in the CONFIG block below. Edit those, then run the script.

------------------------------------------------------------------
SETUP
------------------------------------------------------------------
Requires only the Python standard library (3.7+). No pip installs.

    python3 jerkcity_bot.py

Runs in the foreground and reconnects automatically on drops. Use
tmux/screen, a systemd unit, or `nohup ... &` if you want it to keep
running after you close the terminal. Works the same way under
Termux on Android as it does on a regular Linux/macOS/Windows shell.

------------------------------------------------------------------
FEATURES (mirrors the Android app)
------------------------------------------------------------------
- Connects over TLS or plaintext; optional acceptance of self-signed
  certificates (disables certificate verification -- only use this
  against a server you control/trust)
- TCP keepalive + an application-level PING every 60s to survive
  idle-connection drops on flaky networks/NATs
- Downloads the community quote list from d-flatline/JerkBot's
  jerkcity.lines (entries separated by "%%"), filtering out anything
  under 4 words, and falling back to a small offline list if the
  download fails
- Trigger command (default "!jerkcity"), works in-channel or as a
  direct message to the bot
    - "!jerkcity" alone -> a fully random quote
    - "!jerkcity <word>" -> a random quote containing that word, or a
      "no quote found" reply if nothing matches
- Special-cased reply for the nickname "bananas"
- "Auto Jerk": on ordinary (non-command) channel chatter, roll a
  configurable probability; on a hit, pick a random word over 4
  letters from that message and, if a quote containing it exists,
  post it unprompted. Silent on a miss.

------------------------------------------------------------------
CONTENT NOTE
------------------------------------------------------------------
Jerkcity is NSFW/crude humor. Only point this at channels where
that's welcome.
"""

import socket
import ssl
import random
import re
import sys
import time
import threading
import urllib.request

# ================================================================
# CONFIG -- edit these instead of using a GUI
# ================================================================

# --- Connection tab ---
SERVER = "irc.libera.chat"      # IRC server hostname
PORT = 6697                     # 6697 = TLS, 6667 = plaintext
USE_TLS = True
ALLOW_SELF_SIGNED_CERT = False  # True = skip TLS cert verification.
                                 # Only for a private server you trust;
                                 # this removes protection against
                                 # man-in-the-middle attacks.

# --- Bot tab ---
NICK = "jerkcitybot"
CHANNEL = "#yourchannel"        # channel to join
TRIGGER = "!jerkcity"           # command that triggers a quote reply
                                 # e.g. "!jerkcity pizza" replies with a
                                 # quote containing "pizza"; plain
                                 # "!jerkcity" replies with a random one

# --- Auto Jerk tab ---
AUTO_JERK_ENABLED = False       # if True, the bot may reply to ordinary
                                 # channel chatter without the trigger
AUTO_JERK_PROBABILITY = 10      # 0-100 (%): chance per channel message

# --- Quote source ---
ONLINE_QUOTES = True
QUOTE_LINES_URL = (
    "https://raw.githubusercontent.com/d-flatline/JerkBot/"
    "main/jerkcity.lines"
)
QUOTE_DELIMITER = "%%"
MIN_QUOTE_WORDS = 4              # quotes shorter than this are dropped

# --- Misc ---
RECONNECT_DELAY = 15              # seconds between reconnect attempts
KEEPALIVE_INTERVAL = 60           # seconds between app-level PINGs
SOCKET_TIMEOUT = None             # None = blocking reads (recommended;
                                   # relies on TCP keepalive + app PING
                                   # instead of a read timeout, since a
                                   # short timeout causes false-positive
                                   # "drops" on quiet channels)

# ================================================================

FALLBACK_QUOTES = [
    q for q in [
        "SPIGOT: I AM A GENIUS AND EVERYONE AROUND ME IS AN IDIOT.",
        "DEUCE: I HAVE MADE A TERRIBLE MISTAKE.",
        "PANTS: THIS IS THE WORST DAY OF MY LIFE, AND I HAVE HAD SOME BAD DAYS.",
        "RANDS: I DON'T KNOW WHAT'S GOING ON BUT I DON'T LIKE IT.",
        "T: EVERYTHING IS FINE. NOTHING IS FINE.",
        "DICK: I HAVE A PLAN AND THE PLAN IS TO HAVE NO PLAN.",
        "HANFORD: THIS SEEMED LIKE A GOOD IDEA AT THE TIME.",
        "OZONE: I REGRET EVERYTHING.",
    ]
    if len(q.split()) >= MIN_QUOTE_WORDS
]


def fetch_online_quotes():
    """
    Best-effort download of the community-maintained quote list.
    Returns a list of quote strings (filtered to MIN_QUOTE_WORDS+),
    or an empty list on any failure so the caller can fall back.
    """
    try:
        req = urllib.request.Request(
            QUOTE_LINES_URL, headers={"User-Agent": "jerkcity-bot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[jerkcity_bot] Could not fetch online quotes ({e}); "
              f"using built-in fallback list.")
        return []

    entries = [chunk.strip() for chunk in raw.split(QUOTE_DELIMITER)]
    quotes = [e for e in entries if e and len(e.split()) >= MIN_QUOTE_WORDS]
    return quotes


class JerkcityBot:
    def __init__(self):
        self.quotes = list(FALLBACK_QUOTES)
        if ONLINE_QUOTES:
            fetched = fetch_online_quotes()
            if fetched:
                self.quotes = fetched
                print(f"[jerkcity_bot] Loaded {len(fetched)} quotes online.")
            else:
                print(f"[jerkcity_bot] Using {len(self.quotes)} built-in quotes.")
        self.sock = None
        self._stop = threading.Event()

    def connect(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(30)  # only applies to the connect() call itself
        raw.connect((SERVER, PORT))
        raw.settimeout(SOCKET_TIMEOUT)

        try:
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass  # not available on all platforms; harmless if so

        if USE_TLS:
            if ALLOW_SELF_SIGNED_CERT:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            else:
                ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(raw, server_hostname=SERVER)
        else:
            self.sock = raw

        self.send(f"NICK {NICK}")
        self.send(f"USER {NICK} 0 * :{NICK}")

    def send(self, msg):
        self.sock.sendall((msg + "\r\n").encode("utf-8", errors="replace"))

    def privmsg(self, target, text):
        if len(text) > 400:
            text = text[:400] + "..."
        self.send(f"PRIVMSG {target} :{text}")

    def _keepalive_loop(self):
        # Some mobile/NAT setups silently drop idle TCP connections.
        # Proactively ping the server so there's always outbound
        # traffic keeping the connection alive.
        while not self._stop.is_set():
            time.sleep(KEEPALIVE_INTERVAL)
            if self._stop.is_set():
                return
            try:
                self.send("PING :keepalive")
            except Exception:
                return  # let the main read loop detect and handle it

    def run(self):
        while True:
            self._stop.clear()
            keepalive_thread = None
            try:
                self.connect()
                keepalive_thread = threading.Thread(
                    target=self._keepalive_loop, daemon=True
                )
                keepalive_thread.start()
                self._loop()
            except (OSError, socket.timeout, ssl.SSLError) as e:
                print(f"[jerkcity_bot] Connection error: {e}. "
                      f"Reconnecting in {RECONNECT_DELAY}s...")
            finally:
                self._stop.set()
                try:
                    self.sock.close()
                except Exception:
                    pass
            time.sleep(RECONNECT_DELAY)

    def _loop(self):
        buf = ""
        joined = False
        privmsg_re = re.compile(
            r"^:(?P<nick>[^!]+)!\S+ PRIVMSG (?P<target>\S+) :(?P<text>.*)$"
        )
        while True:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionResetError("Server closed connection")
            buf += chunk.decode("utf-8", errors="replace")
            while "\r\n" in buf:
                line, buf = buf.split("\r\n", 1)
                print(line)

                if line.startswith("PING"):
                    self.send("PONG" + line[4:])
                    continue

                if not joined and " 001 " in line:
                    self.send(f"JOIN {CHANNEL}")
                    joined = True
                    continue

                match = privmsg_re.match(line)
                if not match:
                    continue

                from_nick = match.group("nick")
                target = match.group("target")
                text = match.group("text").strip()

                if from_nick.lower() == NICK.lower():
                    continue

                self._handle_privmsg(from_nick, target, text)

    def _handle_privmsg(self, from_nick, target, text):
        if text.lower().startswith(TRIGGER.lower()):
            reply_target = target if target.startswith("#") else from_nick

            if from_nick.lower() == "bananas":
                self.privmsg(reply_target, "STFU bananas you cretin")
                return

            suffix = text[len(TRIGGER):].strip()
            if suffix:
                matches = [q for q in self.quotes if suffix.lower() in q.lower()]
                if matches:
                    self.privmsg(reply_target, random.choice(matches))
                else:
                    self.privmsg(reply_target, f'No quote found containing "{suffix}".')
            else:
                self.privmsg(reply_target, random.choice(self.quotes))
            return

        # Auto Jerk: only for ordinary channel chatter, never DMs,
        # and only if the message wasn't itself the trigger command.
        if AUTO_JERK_ENABLED and target.startswith("#"):
            if random.randint(0, 99) < AUTO_JERK_PROBABILITY:
                candidate_words = [w for w in re.split(r"[^\w']+", text) if len(w) > 4]
                if candidate_words:
                    word = random.choice(candidate_words)
                    matches = [q for q in self.quotes if word.lower() in q.lower()]
                    if matches:
                        self.privmsg(target, random.choice(matches))
                        print(f'[jerkcity_bot] [auto-jerk] triggered on word "{word}"')


if __name__ == "__main__":
    print(f"[jerkcity_bot] Connecting to {SERVER}:{PORT} as {NICK}, "
          f"joining {CHANNEL}, trigger='{TRIGGER}'"
          + (f", auto-jerk={AUTO_JERK_PROBABILITY}%" if AUTO_JERK_ENABLED else ""))
    bot = JerkcityBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[jerkcity_bot] Stopped.")
        sys.exit(0)
