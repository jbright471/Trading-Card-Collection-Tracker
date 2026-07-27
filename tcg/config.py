"""Centralized configuration for the legacy report and scheduled refresh."""
import os
from pathlib import Path

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')
ALERT_THRESHOLD_PERCENT = float(os.environ.get('ALERT_THRESHOLD_PERCENT', '10.0'))
HTTP_TIMEOUT = float(os.environ.get('HTTP_TIMEOUT', '15'))
HTTP_MAX_RETRIES = int(os.environ.get('HTTP_MAX_RETRIES', '4'))
HTTP_BACKOFF_SECONDS = float(os.environ.get('HTTP_BACKOFF_SECONDS', '1.0'))
HTTP_BACKOFF_MAX_SECONDS = float(os.environ.get('HTTP_BACKOFF_MAX_SECONDS', '20.0'))
SCRYFALL_MIN_INTERVAL_SECONDS = float(os.environ.get('SCRYFALL_MIN_INTERVAL_SECONDS', '0.65'))
REQUEST_DELAY = float(os.environ.get('REQUEST_DELAY', '0.75'))
WISHLIST_COOLDOWN_DAYS = int(os.environ.get('WISHLIST_COOLDOWN_DAYS', '7'))
HISTORY_RETENTION_DAYS = int(os.environ.get('HISTORY_RETENTION_DAYS', '90'))

USER_AGENT = 'MultiTCGTracker/2.0'
DEFAULT_HEADERS = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}

PLACEHOLDER_IMG = "https://via.placeholder.com/250x350?text=No+Image"

DATA_DIR = Path(os.environ.get('TCG_TRACKER_DATA_DIR', '.')).expanduser().resolve()


def _data_file(env_name, default_name):
    configured = Path(os.environ.get(env_name, default_name)).expanduser()
    return str(configured if configured.is_absolute() else DATA_DIR / configured)


COLLECTION_FILE = _data_file('TCG_TRACKER_COLLECTION_FILE', 'my_cards.txt')
WISHLIST_FILE = _data_file('TCG_TRACKER_WISHLIST_FILE', 'wishlist.txt')
WISHLIST_ALERTED_FILE = _data_file('TCG_TRACKER_WISHLIST_ALERTED_FILE', 'wishlist_alerted.json')
WISHLIST_CACHE_FILE = _data_file('TCG_TRACKER_WISHLIST_CACHE_FILE', 'wishlist_cache.json')
LAST_RUN_PRICES = _data_file('TCG_TRACKER_LAST_RUN_PRICES_FILE', 'last_run_prices.json')
LAST_RUN_DATA = _data_file('TCG_TRACKER_LAST_RUN_DATA_FILE', 'last_run_data.json')
HISTORY_FILE = _data_file('TCG_TRACKER_HISTORY_FILE', 'price_history.csv')
CARD_HISTORY_FILE = _data_file('TCG_TRACKER_CARD_HISTORY_FILE', 'card_price_history.json')
GRAPH_FILE = _data_file('TCG_TRACKER_GRAPH_FILE', 'history_graph.png')
EXCEL_FILE = _data_file('TCG_TRACKER_EXCEL_FILE', 'MY_COLLECTION_PRICES.xlsx')
HTML_OUTPUT = _data_file('TCG_TRACKER_HTML_FILE', 'index.html')
