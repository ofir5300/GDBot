import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Wolt API
WOLT_BASE_URL = "https://restaurant-api.wolt.com"
WOLT_SEARCH_URL = f"{WOLT_BASE_URL}/v1/pages/search"
WOLT_ORDER_BASE = "https://wolt.com/en/isr/{city}/restaurant/{slug}"

# Default location (Tel Aviv) — used for Wolt API queries
WOLT_LAT = float(os.environ.get("WOLT_LAT", "32.0853"))
WOLT_LON = float(os.environ.get("WOLT_LON", "34.7818"))

# Polling & TTL
POLL_INTERVAL_SECONDS = 120  # 2 minutes
TTL_HOURS = 4
CLEANUP_INTERVAL_SECONDS = 1800  # 30 minutes

# Database
DB_PATH = Path(__file__).parent / "data" / "gdbot.db"

# Logging
LOG_DIR = Path(__file__).parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "gdbot.log"
