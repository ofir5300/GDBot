# GDBot — Jarvis Runbook

## Purpose
Telegram bot that notifies users when closed Wolt restaurants open for delivery. Runs as a long-lived launchd agent on Jarvis (macOS, Apple Silicon).

## Runtime
- Python 3.11 via `uv` (`/opt/homebrew/bin/uv`)
- Venv at `~/jarvis/projects/GDBot/.venv`
- Process supervised by launchd (`KeepAlive=true`)

## Layout
| What | Path |
|---|---|
| Source | `~/jarvis/projects/GDBot` |
| Data (SQLite) | `~/jarvis/data/GDBot/gdbot.db` (symlinked from `gdbot/data`) |
| Secret (`.env`) | `~/jarvis/secrets/GDBot/.env` (symlinked from repo root) |
| Logs | `~/jarvis/logs/GDBot/bot.log` |
| Plist source | `~/jarvis/scripts/launchd/com.gdbot.bot.plist` |
| Plist link | `~/Library/LaunchAgents/com.gdbot.bot.plist` |

## Install (one-time)
```bash
ssh jarvis '
  mkdir -p ~/jarvis/{projects,data/GDBot,logs/GDBot,secrets/GDBot,scripts/launchd}
  cd ~/jarvis/projects && git clone git@github.com:ofir5300/GDBot.git
  cd GDBot && /opt/homebrew/bin/uv venv --python 3.11 && /opt/homebrew/bin/uv pip install -r requirements.txt
  rm -rf gdbot/data && ln -sfn ~/jarvis/data/GDBot gdbot/data
  ln -sfn ~/jarvis/secrets/GDBot/.env .env
'
# Put TELEGRAM_BOT_TOKEN=... in ~/jarvis/secrets/GDBot/.env (chmod 600)
# Plist lives at ~/jarvis/scripts/launchd/com.gdbot.bot.plist
ssh jarvis '
  ln -sf ~/jarvis/scripts/launchd/com.gdbot.bot.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gdbot.bot.plist
'
```

## Operate
```bash
# Status (PID column: number = running, "-" = stopped)
ssh jarvis 'launchctl list | grep gdbot'

# Tail logs
ssh jarvis 'tail -f ~/jarvis/logs/GDBot/bot.log'

# Restart (also picks up new code)
ssh jarvis 'launchctl kickstart -k gui/$(id -u)/com.gdbot.bot'

# Stop / uninstall
ssh jarvis 'launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.gdbot.bot.plist'
```

## Redeploy (steady state)
```bash
# From Work Mac on a clean main:
git push
ssh jarvis 'cd ~/jarvis/projects/GDBot && git pull --ff-only && /opt/homebrew/bin/uv pip install -r requirements.txt'
ssh jarvis 'launchctl kickstart -k gui/$(id -u)/com.gdbot.bot'
```

## Backups
`~/jarvis/data/GDBot/gdbot.db` — small SQLite. Snapshot with `cp` (safe while running — subscriptions table only).

## Known risks
- **Single-poller constraint**: only ONE process may call `getUpdates` for the bot token. Do not start a second instance anywhere (Pi, local Mac, second Jarvis service) or both will error with `telegram.error.Conflict`.
- **Mac sleep**: if Jarvis sleeps, launchd suspends the bot. Ensure `pmset` keeps Jarvis awake on AC.

## Manual recovery
If the service won't start, run the bot in the foreground to see the real error:
```bash
ssh jarvis 'cd ~/jarvis/projects/GDBot && .venv/bin/python -m gdbot.main'
```
Check `plutil -lint ~/jarvis/scripts/launchd/com.gdbot.bot.plist` if launchctl reports exit code 78.
