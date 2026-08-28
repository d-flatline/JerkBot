# Jerkcity IRC Bot

An IRC bot that replies to a trigger command (or, optionally, jumps
into ordinary chatter unprompted) with a random quote from the
[Jerkcity](https://www.jerkcity.com) webcomic's dialogue archive.

Ships as two independent implementations:

- **Android app** — Kotlin, Material Design GUI, runs as a foreground
  service so it keeps the IRC connection alive in the background.
- **Python script** — a single-file, dependency-free terminal bot for
  Linux/macOS/Windows/Termux. Same feature set, configured by editing
  variables at the top of the file instead of a GUI.

> **Content note:** Jerkcity is NSFW / crude humor. Only point this at
> channels where that's welcome. This project reproduces no Jerkcity
> artwork or characters — the app icon is an original design, and the
> quote text is pulled live from a third-party community archive
> rather than bundled with this repo.

---

## Features

- **Trigger command** (default `!jerkcity`), works in-channel or as a
  direct message to the bot
  - `!jerkcity` alone → a fully random quote
  - `!jerkcity <word>` → a random quote containing that word, or a
    "no quote found" reply if nothing matches
- **Auto Jerk** — an opt-in mode where the bot doesn't wait for the
  trigger. On every ordinary channel message, it rolls a configurable
  probability (0–100%); on a hit, it picks a random word over 4
  letters from that message and, if a quote containing it exists,
  posts it unprompted. Silent on a miss. Off by default.
- **Live quote list** — downloads
  [`jerkcity.lines`](https://github.com/d-flatline/JerkBot/blob/main/jerkcity.lines)
  from d-flatline/JerkBot at connect time (entries separated by `%%`),
  filters out anything under 4 words, and falls back to a small
  built-in offline list if the download fails.
- **TLS support**, including an option to trust self-signed
  certificates for private/internal IRC servers.
- **Connection resilience** — TCP keepalive plus an application-level
  `PING` every 60 seconds, so the bot survives idle-connection drops
  common on mobile networks and NATs.
- A hard-coded easter egg: any command from someone named `bananas`
  gets `STFU bananas you cretin` instead of a quote.

---

## Android App

A Kotlin app with a tabbed Material Design interface:

| Tab | Contents |
|---|---|
| **Connection** | Server, port, TLS switch, self-signed cert switch |
| **Bot** | Nickname, channel, trigger command |
| **Auto Jerk** | Enable switch, probability slider |
| **Log** | Live scrolling raw IRC traffic |

Start/Stop controls and a color-coded status line (grey = stopped,
amber = connecting, green = connected, red = error) stay visible under
every tab.

**Under the hood:**
- Runs as a foreground `Service` with a persistent notification, so
  Android doesn't kill the connection when the app is backgrounded
- Holds a partial wake lock and a Wi-Fi lock, and prompts for battery-
  optimization exemption on Start — all aimed at preventing Android
  itself from silently aborting the socket (`Software caused
  connection abort`) during Doze/App Standby
- Settings persist across launches via `SharedPreferences`

### Building

This repo ships the full Android Studio project source, not a
prebuilt APK.

1. Install [Android Studio](https://developer.android.com/studio).
2. Open the `JerkcityIRC/` folder as a project.
3. Let Gradle sync (needs internet the first time).
4. **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
5. Find the output under
   `app/build/outputs/apk/debug/app-debug.apk`, copy it to your
   device, and install it (allow "install from unknown sources" for
   whatever app you use to open it).

This is unsigned debug output. For a signed release build, use
Android Studio's **Build → Generate Signed Bundle / APK** wizard.

---

## Python Script

A single file, `jerkcity_bot.py`, with no dependencies beyond the
Python 3 standard library. Every setting that's a field in the Android
app is instead a variable in the `CONFIG` block at the top of the
file — edit those, then run it.

```bash
python3 jerkcity_bot.py
```

Key config variables:

```python
SERVER = "irc.libera.chat"
PORT = 6697
USE_TLS = True
ALLOW_SELF_SIGNED_CERT = False

NICK = "jerkcitybot"
CHANNEL = "#yourchannel"
TRIGGER = "!jerkcity"

AUTO_JERK_ENABLED = False
AUTO_JERK_PROBABILITY = 10   # 0-100 (%)
```

Works identically in a normal terminal, inside [Termux](https://termux.dev)
on Android, under `tmux`/`screen`, or as a `systemd` service if you
want it to run persistently. On Termux, run `termux-wake-lock` first
so Android doesn't suspend the process.

---

## Configuration Reference

| Setting | Android tab | Python variable | Description |
|---|---|---|---|
| Server address | Connection | `SERVER` | IRC server hostname |
| Port | Connection | `PORT` | 6697 = TLS, 6667 = plaintext (typical) |
| Use TLS | Connection | `USE_TLS` | Encrypt the connection |
| Trust self-signed certs | Connection | `ALLOW_SELF_SIGNED_CERT` | Skips certificate verification — only for a server you control |
| Nickname | Bot | `NICK` | Bot's IRC nick |
| Channel | Bot | `CHANNEL` | Channel to join, e.g. `#yourchannel` |
| Trigger command | Bot | `TRIGGER` | Command prefix that requests a quote |
| Auto Jerk enabled | Auto Jerk | `AUTO_JERK_ENABLED` | Allow unprompted replies to channel chatter |
| Auto Jerk probability | Auto Jerk | `AUTO_JERK_PROBABILITY` | % chance per channel message |

---

## Disclaimer

This is an unofficial fan project. Jerkcity and its characters are
the property of their creator; this bot only links out to a
third-party, community-maintained quote archive rather than bundling
or redistributing comic artwork.
