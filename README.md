# GDBot — Wolt Restaurant Notifier

> Never miss your favorite restaurant opening again.

GDBot is a Telegram bot that watches [Wolt](https://wolt.com) restaurants and pings you the moment they open for delivery. Search, subscribe, and get notified — all from Telegram.

## How It Works

```
You: "shawarma hakarim"
GDBot: 🔶 Shawarma HaKarim — Pickup only (no delivery)
       Want me to notify you when delivery opens?
You: [Yes, notify me]
       ... 20 minutes later ...
GDBot: 🟢 Shawarma HaKarim is now OPEN for orders!
       👉 Order here: https://wolt.com/...
```

1. **Search** — Type any restaurant name, GDBot searches Wolt in real time
2. **Subscribe** — If it's closed or pickup-only, tap to subscribe
3. **Get notified** — GDBot polls every 2 minutes and messages you when delivery opens
4. **Auto-cleanup** — Subscriptions expire after 4 hours or at midnight (no stale alerts)

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
| `/mysubs` | View & manage your active subscriptions |
| `/debug <name>` | Show raw Wolt API status for a venue |
| `/testnotify` | Test that notifications are reaching you |
| `/help` | Show help & active subscriptions |
| `/cancel` | Cancel current action |

## Setup

### Prerequisites

- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Install & Run

```bash
git clone https://github.com/ofir5300/GDBot.git
cd GDBot

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your bot token

python3 -m gdbot.main
```

### Configuration

All config lives in environment variables (via `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Your bot token from BotFather |
| `WOLT_LAT` | `32.0853` | Latitude for Wolt searches |
| `WOLT_LON` | `34.7818` | Longitude for Wolt searches |

Default location is Tel Aviv. Change the coordinates to search restaurants in a different city.

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

- **Async everything** — built on `python-telegram-bot` + `aiohttp` + `aiosqlite`
- **SQLite with WAL mode** — lightweight, zero-config persistence
- **Confirmation re-check** — polls twice (3s apart) before notifying, to avoid false positives
- **Broadcast model** — when a venue opens, all subscribed users get notified

## License

MIT
