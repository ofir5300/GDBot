import logging
from datetime import datetime, timedelta

import aiosqlite

from gdbot.config import DB_PATH, TTL_HOURS

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    slug TEXT NOT NULL,
    restaurant_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    active INTEGER NOT NULL DEFAULT 1
);
"""

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    first_name TEXT,
    registered_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_subs_active ON subscriptions(active, slug);
"""

# Prevent duplicate active subscriptions for same user+restaurant
CREATE_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_subs_unique_active
ON subscriptions(user_id, slug) WHERE active = 1;
"""


async def _get_conn() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    return conn


async def init_db() -> None:
    conn = await _get_conn()
    try:
        await conn.execute(CREATE_TABLE)
        await conn.execute(CREATE_USERS_TABLE)
        await conn.execute(CREATE_INDEX)
        await conn.execute(CREATE_UNIQUE)
        await conn.commit()
        logger.info("Database initialized")
    finally:
        await conn.close()


async def register_user(user_id: int, chat_id: int, first_name: str = None) -> bool:
    """Register a user. Returns True if newly registered."""
    conn = await _get_conn()
    try:
        await conn.execute(
            "INSERT OR IGNORE INTO users (chat_id, user_id, first_name) VALUES (?, ?, ?)",
            (chat_id, user_id, first_name),
        )
        await conn.commit()
        return conn.total_changes > 0
    finally:
        await conn.close()


async def get_all_registered_chat_ids() -> list[int]:
    """Returns all registered user chat IDs."""
    conn = await _get_conn()
    try:
        cursor = await conn.execute("SELECT chat_id FROM users")
        rows = await cursor.fetchall()
        return [r["chat_id"] for r in rows]
    finally:
        await conn.close()


async def add_subscription(user_id: int, chat_id: int, slug: str, restaurant_name: str) -> bool:
    """Add a subscription. Returns True if added, False if already exists."""
    conn = await _get_conn()
    try:
        await conn.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, chat_id, slug, restaurant_name) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, slug, restaurant_name),
        )
        await conn.commit()
        return conn.total_changes > 0
    finally:
        await conn.close()


async def remove_subscription(user_id: int, slug: str) -> None:
    conn = await _get_conn()
    try:
        await conn.execute(
            "UPDATE subscriptions SET active = 0 WHERE user_id = ? AND slug = ? AND active = 1",
            (user_id, slug),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_user_subscriptions(user_id: int) -> list[dict]:
    """Returns list of {slug, restaurant_name, created_at} for active subs."""
    conn = await _get_conn()
    try:
        cursor = await conn.execute(
            "SELECT slug, restaurant_name, created_at FROM subscriptions WHERE user_id = ? AND active = 1",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [{"slug": r["slug"], "restaurant_name": r["restaurant_name"], "created_at": r["created_at"]} for r in rows]
    finally:
        await conn.close()


async def get_all_active_subscriptions() -> dict[str, list[dict]]:
    """Returns {slug: [{user_id, chat_id, restaurant_name}, ...]} for all active subs."""
    conn = await _get_conn()
    try:
        cursor = await conn.execute(
            "SELECT user_id, chat_id, slug, restaurant_name FROM subscriptions WHERE active = 1"
        )
        rows = await cursor.fetchall()
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            slug = r["slug"]
            if slug not in grouped:
                grouped[slug] = []
            grouped[slug].append({
                "user_id": r["user_id"],
                "chat_id": r["chat_id"],
                "restaurant_name": r["restaurant_name"],
            })
        return grouped
    finally:
        await conn.close()


async def cleanup_expired() -> list[dict]:
    """Deactivate subscriptions older than TTL_HOURS. Returns affected subs for notification."""
    cutoff = (datetime.now() - timedelta(hours=TTL_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = await _get_conn()
    try:
        cursor = await conn.execute(
            "SELECT user_id, chat_id, slug, restaurant_name FROM subscriptions WHERE active = 1 AND created_at < ?",
            (cutoff,),
        )
        expired = [dict(r) for r in await cursor.fetchall()]
        if expired:
            await conn.execute(
                "UPDATE subscriptions SET active = 0 WHERE active = 1 AND created_at < ?",
                (cutoff,),
            )
            await conn.commit()
            logger.info("Cleaned up %d expired subscriptions", len(expired))
        return expired
    finally:
        await conn.close()


async def cleanup_all_active() -> list[dict]:
    """Midnight wipe — deactivate all remaining active subs. Returns affected subs."""
    conn = await _get_conn()
    try:
        cursor = await conn.execute(
            "SELECT user_id, chat_id, slug, restaurant_name FROM subscriptions WHERE active = 1"
        )
        active = [dict(r) for r in await cursor.fetchall()]
        if active:
            await conn.execute("UPDATE subscriptions SET active = 0 WHERE active = 1")
            await conn.commit()
            logger.info("Midnight cleanup: deactivated %d subscriptions", len(active))
        return active
    finally:
        await conn.close()


async def startup_purge() -> list[dict]:
    """Crash recovery — remove subs older than TTL_HOURS on startup. Returns purged subs."""
    expired = await cleanup_expired()
    if expired:
        logger.info("Startup purge: cleaned %d stale subscriptions", len(expired))
    return expired


async def get_all_known_chat_ids() -> list[int]:
    """Returns all distinct chat_ids that ever had a subscription."""
    conn = await _get_conn()
    try:
        cursor = await conn.execute("SELECT DISTINCT chat_id FROM subscriptions")
        rows = await cursor.fetchall()
        return [r["chat_id"] for r in rows]
    finally:
        await conn.close()


async def get_active_subs_by_chat() -> dict[int, list[str]]:
    """Returns {chat_id: [restaurant_name, ...]} for all active subs."""
    conn = await _get_conn()
    try:
        cursor = await conn.execute(
            "SELECT chat_id, restaurant_name FROM subscriptions WHERE active = 1"
        )
        rows = await cursor.fetchall()
        grouped: dict[int, list[str]] = {}
        for r in rows:
            chat_id = r["chat_id"]
            if chat_id not in grouped:
                grouped[chat_id] = []
            grouped[chat_id].append(r["restaurant_name"])
        return grouped
    finally:
        await conn.close()


async def deactivate_subscription_by_slug(slug: str) -> None:
    """Deactivate all active subscriptions for a given slug (used after notification)."""
    conn = await _get_conn()
    try:
        await conn.execute(
            "UPDATE subscriptions SET active = 0 WHERE slug = ? AND active = 1",
            (slug,),
        )
        await conn.commit()
    finally:
        await conn.close()
