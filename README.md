# GDBot - Wolt Restaurant Notifier

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![Wolt](https://img.shields.io/badge/Wolt-API-00C2E8?logo=wolt&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

<p align="center">
  <img src="assets/gdb.jpg" alt="GDB Burger" width="300" />
</p>

> Born out of my obsession with **GDB Iben Gabirol** and the pain of checking Wolt every 5 minutes to see if they're open for delivery. Now the bot does it for me.

GDBot is a Telegram bot that watches [Wolt](https://wolt.com) restaurants and pings you the moment they open for delivery.

## How It Works

```
You: "vitrina"
GDBot: 🔶 Vitrina Iben Gabirol - Pickup only (no delivery)
       Want me to notify you when delivery opens?
You: [Yes, notify me]
       ... 20 minutes later ...
GDBot: 🟢 Vitrina Iben Gabirol is now OPEN for orders!
       👉 Order here: https://wolt.com/...
```

1. **Search** - Type any restaurant name, GDBot searches Wolt in real time
2. **Subscribe** - If it's closed or pickup-only, tap to subscribe
3. **Get notified** - GDBot polls every 2 minutes and messages you when delivery opens
4. **Auto-cleanup** - Subscriptions expire after 4 hours or at midnight

## Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | Open for delivery |
| 🔶 | Pickup only (no delivery) |
| ❌ | Closed |

## Commands

| Command | Description |
|---------|-------------|
| `/search <name>` | Search for a restaurant (or just type the name) |
| `/mysubs` | View & manage active subscriptions |
| `/debug <name>` | Show raw Wolt API status for a venue |
| `/testnotify` | Test that notifications reach you |
| `/help` | Show help & active subscriptions |
| `/cancel` | Cancel current action |

## Setup

**Prerequisites:** Python 3.10+, a Telegram bot token from [@BotFather](https://t.me/BotFather)

```bash
git clone https://github.com/ofir5300/GDBot.git
cd GDBot
pip install -r requirements.txt
cp .env.example .env   # add your bot token
python3 -m gdbot.main
```

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Bot token from BotFather |
| `WOLT_LAT` | `32.0853` | Latitude for Wolt searches |
| `WOLT_LON` | `34.7818` | Longitude for Wolt searches |

Default location is Tel Aviv.

## Architecture

```
gdbot/
├── main.py          # Entry point, bot setup, job scheduling
├── handlers.py      # Telegram command & callback handlers
├── wolt_client.py   # Wolt API client (search + status checks)
├── jobs.py          # Scheduled polling, TTL cleanup, midnight reset
├── db.py            # SQLite database layer
└── config.py        # Environment variables & constants
```

Async stack: `python-telegram-bot` + `aiohttp` + `aiosqlite` with SQLite WAL mode. Polls twice (3s apart) before notifying to avoid false positives. Broadcast model - when a venue opens, all subscribed users get notified.

## License

MIT
