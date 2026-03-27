import asyncio
import logging

from telegram.ext import ContextTypes

from gdbot import db, wolt_client

logger = logging.getLogger(__name__)


async def _broadcast(context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs) -> None:
    """Send a message to ALL registered users."""
    chat_ids = await db.get_all_registered_chat_ids()
    for chat_id in chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except Exception as e:
            logger.error("Failed to broadcast to chat %d: %s", chat_id, e)


async def poll_subscriptions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check all active subscriptions and notify users when restaurants open."""
    subs_by_slug = await db.get_all_active_subscriptions()
    if not subs_by_slug:
        return

    logger.info("Polling %d unique restaurants", len(subs_by_slug))

    stats = {"open": 0, "closed": 0, "pickup_only": 0, "error": 0}

    for slug, subscribers in subs_by_slug.items():
        status = await wolt_client.check_restaurant_status(slug)
        if status is None:
            logger.warning("Could not check status for %s, skipping", slug)
            stats["error"] += 1
            continue

        online = status["online"]
        delivers = status.get("delivers", False)
        logger.info(
            "Status for %s (%s): online=%s, delivers=%s",
            slug, status["name"], online, delivers,
        )

        if not online:
            logger.debug("Skipping %s — closed (offline)", slug)
            stats["closed"] += 1
            continue

        if not delivers:
            logger.info("Skipping %s — pickup only (online but not delivering)", slug)
            stats["pickup_only"] += 1
            continue

        # Confirmation re-check: wait and query again to avoid false positives
        logger.info("Restaurant %s appears OPEN, confirming with second check...", slug)
        await asyncio.sleep(3)
        recheck = await wolt_client.check_restaurant_status(slug)
        if recheck is None or not recheck.get("online") or not recheck.get("delivers"):
            logger.warning(
                "Confirmation failed for %s — online=%s, delivers=%s. Skipping notification.",
                slug,
                recheck.get("online") if recheck else None,
                recheck.get("delivers") if recheck else None,
            )
            stats["closed"] += 1
            continue

        stats["open"] += 1
        # Restaurant confirmed open for delivery — broadcast to ALL users
        logger.info("Restaurant %s confirmed OPEN! Broadcasting to all users", slug)
        await _broadcast(
            context,
            f"\U0001f7e2 {status['name']} is now OPEN for orders!\n\n"
            f"\U0001f449 Order here: {status['order_url']}",
        )

        await db.deactivate_subscription_by_slug(slug)

    logger.info(
        "Poll complete: %d venues — %d open, %d closed, %d pickup-only, %d errors",
        sum(stats.values()), stats["open"], stats["closed"],
        stats["pickup_only"], stats["error"],
    )


async def ttl_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove subscriptions older than TTL_HOURS and broadcast to all users."""
    expired = await db.cleanup_expired()
    if not expired:
        return

    # Collect unique restaurant names
    names = list({sub["restaurant_name"] for sub in expired})
    names_list = "\n".join(f"  - {n}" for n in names)
    await _broadcast(
        context,
        f"\u23f0 <b>Subscriptions expired</b> (4 hour limit)\n\n"
        f"The following {len(names)} subscription(s) were removed:\n"
        f"{names_list}\n\n"
        f"The restaurants didn't open in time. "
        f"Type a restaurant name to subscribe again!",
        parse_mode="HTML",
    )


async def midnight_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Daily reset at midnight — deactivate all active subscriptions and broadcast."""
    active = await db.cleanup_all_active()
    if not active:
        return

    names = list({sub["restaurant_name"] for sub in active})
    names_list = "\n".join(f"  - {n}" for n in names)
    await _broadcast(
        context,
        f"\U0001f319 <b>Midnight reset</b>\n\n"
        f"All subscriptions have been cleared for the day.\n"
        f"Removed {len(names)} subscription(s):\n"
        f"{names_list}\n\n"
        f"Type a restaurant name to subscribe again tomorrow!",
        parse_mode="HTML",
    )
