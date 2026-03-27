import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from gdbot import db, wolt_client

logger = logging.getLogger(__name__)

SELECTING_RESTAURANT = 0

# Compact callback prefixes (Telegram limits callback_data to 64 bytes)
# Format: "PREFIX:slug" — Wolt slugs are alphanumeric + hyphens, so ":" is safe
CB_CHECK = "c"   # c:slug — check restaurant status
CB_SUB = "s"     # s:slug — subscribe to notifications
CB_NO = "n"      # n — decline subscription
CB_UNSUB = "u"   # u:slug — unsubscribe


def _cb(prefix: str, slug: str = "") -> str:
    return f"{prefix}:{slug}" if slug else prefix


def _parse_cb(data: str) -> tuple[str, str]:
    """Parse 'prefix:slug' callback data. Returns (prefix, slug)."""
    if ":" in data:
        prefix, slug = data.split(":", 1)
        return prefix, slug
    return data, ""


HELP_TEXT = (
    "<b>GDBot</b> — Wolt Restaurant Notifier\n\n"
    "I'll notify you when a closed Wolt restaurant opens for delivery.\n\n"
    "<b>How to use:</b>\n"
    "Just type a restaurant name and I'll search Wolt for you.\n\n"
    "<b>Commands:</b>\n"
    "/search &lt;name&gt; — Search for a restaurant\n"
    "/mysubs — View your active subscriptions\n"
    "/testnotify — Test notification delivery\n"
    "/debug &lt;name&gt; — Show raw API status for a venue\n"
    "/help — Show this help message\n"
    "/cancel — Cancel current action\n\n"
    "<b>How it works:</b>\n"
    "1. Search for a restaurant\n"
    "2. If it's closed or pickup-only, subscribe for notifications\n"
    "3. I check every 2 minutes and notify you when delivery opens\n"
    "4. Subscriptions expire after 4 hours or at midnight\n\n"
    "<b>Status icons:</b>\n"
    "\u2705 Open for delivery\n"
    "\U0001f536 Pickup only (no delivery)\n"
    "\u274c Closed"
)


async def _register(update: Update) -> None:
    """Register the user if not already known."""
    user = update.effective_user
    if user:
        await db.register_user(user.id, update.effective_chat.id, user.first_name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _register(update)
    user_id = update.effective_user.id
    subs = await db.get_user_subscriptions(user_id)

    text = HELP_TEXT
    if subs:
        text += "\n\n<b>Your active subscriptions:</b>\n"
        for i, s in enumerate(subs, 1):
            text += f"{i}. {s['restaurant_name']}\n"

    await update.message.reply_text(text, parse_mode="HTML")
    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    subs = await db.get_user_subscriptions(user_id)

    text = HELP_TEXT
    if subs:
        text += "\n\n<b>Your active subscriptions:</b>\n"
        for i, s in enumerate(subs, 1):
            text += f"{i}. {s['restaurant_name']}\n"

    await update.message.reply_text(text, parse_mode="HTML")


async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle plain text messages as search queries."""
    await _register(update)
    context.args = update.message.text.strip().split()
    return await search(update, context)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _register(update)
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Just type a restaurant name to search!\nExample: shawarma")
        return ConversationHandler.END

    await update.message.chat.send_action("typing")
    results = await wolt_client.search_restaurants(query)

    if not results:
        await update.message.reply_text(f'No restaurants found for "{query}". Try a different search term.')
        return ConversationHandler.END

    # Store results in user_data so we can look up name/city later without stuffing it into callback
    context.user_data["search_results"] = {r["slug"]: r for r in results}

    buttons = []
    for r in results:
        if r.get("online") and r.get("delivers"):
            status_icon = "\u2705"
        elif r.get("online") and not r.get("delivers"):
            status_icon = "\U0001f536"  # pickup only
        else:
            status_icon = "\u274c"
        buttons.append([InlineKeyboardButton(f"{status_icon} {r['name']}", callback_data=_cb(CB_CHECK, r["slug"]))])

    await update.message.reply_text(
        f'Found {len(results)} results for "{query}".\nSelect a restaurant:',
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECTING_RESTAURANT


async def restaurant_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    prefix, slug = _parse_cb(query.data)

    if prefix == CB_CHECK:
        return await _handle_check(query, context, slug)
    elif prefix == CB_SUB:
        return await _handle_subscribe(query, context, slug)
    elif prefix == CB_NO:
        await query.edit_message_text("No problem! Use /search anytime to look for another restaurant.")
        return ConversationHandler.END

    return ConversationHandler.END


async def _handle_check(query, context: ContextTypes.DEFAULT_TYPE, slug: str) -> int:
    # Use cached search result if available (avoids extra API call)
    cached = context.user_data.get("search_results", {}).get(slug)
    if cached:
        status = {
            "online": cached["online"],
            "delivers": cached.get("delivers", False),
            "name": cached["name"],
            "order_url": cached["order_url"],
        }
    else:
        status = await wolt_client.check_restaurant_status(slug)

    if status is None:
        await query.edit_message_text("Could not check restaurant status. Try searching again.")
        return ConversationHandler.END

    # Store checked restaurant info for subscribe step
    context.user_data["last_checked"] = {"slug": slug, "name": status["name"]}

    online = status["online"]
    delivers = status.get("delivers", False)

    if online and delivers:
        await query.edit_message_text(
            f"<b>{status['name']}</b> is OPEN for orders!\n\n"
            f'<a href="{status["order_url"]}">Order here</a>',
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # Restaurant is closed or pickup-only — offer subscription
    if online and not delivers:
        msg = f"\U0001f536 {status['name']} — <b>Pickup only</b> (no delivery)\n\nWant me to notify you when delivery opens?"
    else:
        msg = f"{status['name']} is currently CLOSED.\n\nWant me to notify you when it opens?"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes, notify me", callback_data=_cb(CB_SUB, slug)),
            InlineKeyboardButton("No thanks", callback_data=_cb(CB_NO)),
        ]
    ])
    await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="HTML")
    return SELECTING_RESTAURANT


async def _handle_subscribe(query, context: ContextTypes.DEFAULT_TYPE, slug: str) -> int:
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # Get name from last_checked or search_results
    last = context.user_data.get("last_checked", {})
    search_results = context.user_data.get("search_results", {})
    name = last.get("name") or search_results.get(slug, {}).get("name") or slug

    added = await db.add_subscription(user_id, chat_id, slug, name)
    if added:
        await query.edit_message_text(
            f"Subscribed to {name}!\n\n"
            "I'll check every 2 minutes and notify you when it opens.\n"
            "Subscription expires after 4 hours or at midnight."
        )
    else:
        await query.edit_message_text(f"You're already subscribed to {name}.")

    return ConversationHandler.END


async def mysubs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    subs = await db.get_user_subscriptions(user_id)

    if not subs:
        await update.message.reply_text("You have no active subscriptions.\nUse /search to find a restaurant.")
        return

    buttons = []
    lines = ["Your active subscriptions:\n"]
    for i, s in enumerate(subs, 1):
        lines.append(f"{i}. {s['restaurant_name']} (since {s['created_at']})")
        buttons.append([InlineKeyboardButton(
            f"Remove: {s['restaurant_name']}",
            callback_data=_cb(CB_UNSUB, s["slug"]),
        )])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
    )


async def unsub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    prefix, slug = _parse_cb(query.data)
    if prefix != CB_UNSUB:
        return

    user_id = query.from_user.id
    await db.remove_subscription(user_id, slug)
    await query.edit_message_text("Removed subscription. Use /search to subscribe again.")


async def testnotify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a test notification to verify Telegram delivery is working."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # 1. Send a fake open notification
    await update.message.reply_text(
        "\U0001f7e2 <b>TEST</b> — Restaurant is now OPEN for orders!\n\n"
        "\U0001f449 This is a test notification. If you see this, delivery is working.",
        parse_mode="HTML",
    )

    # 2. Show diagnostics
    subs = await db.get_user_subscriptions(user_id)
    job_queue = context.application.job_queue
    poll_jobs = [j for j in job_queue.jobs() if j.callback.__name__ == "poll_subscriptions"]

    lines = [
        "<b>Diagnostics:</b>",
        f"Chat ID: <code>{chat_id}</code>",
        f"Active subscriptions: {len(subs)}",
        f"Polling job active: {'Yes' if poll_jobs else 'No'}",
    ]
    if subs:
        lines.append("\n<b>Subscribed to:</b>")
        for s in subs:
            lines.append(f"  - {s['restaurant_name']} (<code>{s['slug']}</code>)")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def debug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show raw API fields for a venue. Usage: /debug <slug or search query>"""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /debug hudson lilienblum")
        return

    await update.message.chat.send_action("typing")
    results = await wolt_client.search_restaurants(query)
    if not results:
        await update.message.reply_text(f'No results for "{query}"')
        return

    lines = []
    for r in results[:3]:
        lines.append(
            f"<b>{r['name']}</b> (<code>{r['slug']}</code>)\n"
            f"  online: <code>{r['online']}</code>\n"
            f"  delivers: <code>{r['delivers']}</code>\n"
            f"  → Bot verdict: "
            + (
                "OPEN for delivery" if r["online"] and r["delivers"]
                else "Pickup only" if r["online"] and not r["delivers"]
                else "CLOSED"
            )
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled. Use /search to start a new search.")
    return ConversationHandler.END


# Build the ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("search", search),
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_search),
    ],
    states={
        SELECTING_RESTAURANT: [CallbackQueryHandler(restaurant_selected)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", start),
        CommandHandler("search", search),
    ],
)

# Standalone handler for unsub buttons from /mysubs (outside conversation)
unsub_handler = CallbackQueryHandler(unsub_callback, pattern=r"^u:")
