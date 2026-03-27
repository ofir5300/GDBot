import logging
from datetime import time

from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler

from gdbot import db
from gdbot.config import (
    CLEANUP_INTERVAL_SECONDS,
    LOG_FILE,
    POLL_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TTL_HOURS,
)
from gdbot.handlers import HELP_TEXT, conv_handler, debug_cmd, help_cmd, mysubs, start, testnotify, unsub_handler
from gdbot.jobs import midnight_cleanup, poll_subscriptions, ttl_cleanup

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    """Initialize DB, purge stale subs, schedule jobs, send boot message."""
    await db.init_db()
    purged = await db.startup_purge()

    # Build purge info grouped by chat_id
    purged_by_chat: dict[int, list[str]] = {}
    for sub in purged:
        cid = sub["chat_id"]
        if cid not in purged_by_chat:
            purged_by_chat[cid] = []
        purged_by_chat[cid].append(sub["restaurant_name"])

    # Set Telegram commands menu
    await application.bot.set_my_commands([
        BotCommand("start", "Welcome & status"),
        BotCommand("search", "Search for a restaurant"),
        BotCommand("mysubs", "View active subscriptions"),
        BotCommand("testnotify", "Test notification delivery"),
        BotCommand("debug", "Show raw API status for a venue"),
        BotCommand("help", "Show help"),
        BotCommand("cancel", "Cancel current action"),
    ])

    # Schedule jobs
    jq = application.job_queue
    jq.run_repeating(poll_subscriptions, interval=POLL_INTERVAL_SECONDS, first=10)
    jq.run_repeating(ttl_cleanup, interval=CLEANUP_INTERVAL_SECONDS, first=60)
    jq.run_daily(midnight_cleanup, time=time(0, 0, 0))

    # Migrate existing chat_ids from subscriptions to users table
    legacy_chat_ids = await db.get_all_known_chat_ids()
    for cid in legacy_chat_ids:
        await db.register_user(user_id=0, chat_id=cid)

    # Send boot message to all registered users
    all_chat_ids = await db.get_all_registered_chat_ids()
    active_by_chat = await db.get_active_subs_by_chat()

    for chat_id in all_chat_ids:
        text = HELP_TEXT + "\n\n<b>GDBot is back online!</b>"

        # Show what was purged on startup
        purged_names = purged_by_chat.get(chat_id)
        if purged_names:
            names_str = ", ".join(purged_names)
            text += (
                f"\n\nExpired subscriptions cleared (older than {TTL_HOURS}h): "
                f"{names_str}"
            )

        # Show remaining active subs
        active_names = active_by_chat.get(chat_id)
        if active_names:
            names_list = "\n".join(f"  {i}. {n}" for i, n in enumerate(active_names, 1))
            text += f"\n\nWatching {len(active_names)} restaurant(s):\n{names_list}"
        else:
            text += "\n\nNo active subscriptions. Type a restaurant name to search!"

        try:
            await application.bot.send_message(
                chat_id=chat_id, text=text, parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Failed to send boot message to chat %d: %s", chat_id, e)

    logger.info(
        "GDBot started — polling every %ds, TTL cleanup every %ds",
        POLL_INTERVAL_SECONDS,
        CLEANUP_INTERVAL_SECONDS,
    )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set. Create a .env file (see .env.example).")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysubs", mysubs))
    app.add_handler(CommandHandler("testnotify", testnotify))
    app.add_handler(CommandHandler("debug", debug_cmd))
    app.add_handler(unsub_handler)

    logger.info("Starting GDBot...")
    app.run_polling()


if __name__ == "__main__":
    main()
