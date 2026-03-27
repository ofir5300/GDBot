import asyncio
import logging
import ssl

import aiohttp
import certifi

from gdbot.config import WOLT_SEARCH_URL, WOLT_ORDER_BASE, WOLT_LAT, WOLT_LON

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)
SSL_CTX = ssl.create_default_context(cafile=certifi.where())
MAX_RESULTS = 10


async def _post_search(query: str) -> dict | None:
    """POST to Wolt search API with one retry on failure."""
    payload = {"q": query, "lat": WOLT_LAT, "lon": WOLT_LON}
    for attempt in range(2):
        try:
            connector = aiohttp.TCPConnector(ssl=SSL_CTX)
            async with aiohttp.ClientSession(timeout=TIMEOUT, connector=connector) as session:
                async with session.post(WOLT_SEARCH_URL, json=payload) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.warning("Wolt search returned %d for q=%s", resp.status, query)
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == 0:
                logger.warning("Wolt API request failed (%s), retrying in 2s...", e)
                await asyncio.sleep(2)
            else:
                logger.error("Wolt API request failed after retry: %s", e)
                return None
    return None


def _extract_venues(data: dict) -> list[dict]:
    """Extract venue dicts from search response sections."""
    venues = []
    for section in data.get("sections", []):
        for item in section.get("items", []):
            venue = item.get("venue")
            if venue and venue.get("slug"):
                venues.append(venue)
    return venues


async def search_restaurants(query: str) -> list[dict]:
    """
    Search Wolt for restaurants matching query.
    Returns list of {slug, name, online, city, order_url} dicts (max 10).
    """
    data = await _post_search(query)
    if data is None:
        return []

    city = data.get("city", "tel-aviv")
    venues = _extract_venues(data)

    results = []
    for v in venues[:MAX_RESULTS]:
        slug = v["slug"]
        results.append({
            "slug": slug,
            "name": v.get("name", slug),
            "online": v.get("online", False),
            "delivers": v.get("delivers", False),
            "city": city,
            "order_url": WOLT_ORDER_BASE.format(city=city, slug=slug),
        })
    return results


async def check_restaurant_status(slug: str) -> dict | None:
    """
    Check if a restaurant is online by searching for its slug.
    Returns {online, name, order_url} or None on error.
    """
    data = await _post_search(slug)
    if data is None:
        return None

    city = data.get("city", "tel-aviv")
    venues = _extract_venues(data)

    # Find exact slug match first, then fall back to first result
    for v in venues:
        if v["slug"] == slug:
            return {
                "online": v.get("online", False),
                "delivers": v.get("delivers", False),
                "name": v.get("name", slug),
                "order_url": WOLT_ORDER_BASE.format(city=city, slug=slug),
            }

    # No exact match — slug may have changed or restaurant removed
    if venues:
        v = venues[0]
        logger.warning("No exact match for slug %s, best match: %s", slug, v["slug"])
        return None

    return None
