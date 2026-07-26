"""HTTP helper with timeout, Scryfall pacing, and 429 backoff."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime

from tcg.config import (
    DEFAULT_HEADERS,
    HTTP_BACKOFF_MAX_SECONDS,
    HTTP_BACKOFF_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT,
    SCRYFALL_MIN_INTERVAL_SECONDS,
)

_SCRYFALL_LOCK = threading.Lock()
_LAST_SCRYFALL_REQUEST_AT = 0.0


def get_json(url, headers=None):
    """GET JSON with timeout, Retry-After support, and Scryfall pacing."""
    _require_https(url)
    last_error = None
    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            _pace_scryfall_request(url)
            req = urllib.request.Request(url, headers=headers or DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:  # nosec B310
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt >= HTTP_MAX_RETRIES:
                raise
            delay = _retry_delay_seconds(exc, attempt)
            print(f"HTTP 429 from {urllib.parse.urlparse(url).netloc}; retrying in {delay:.1f}s")
            time.sleep(delay)

    raise last_error


def _require_https(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Only HTTPS API URLs are allowed")


def _pace_scryfall_request(url):
    if urllib.parse.urlparse(url).netloc.lower() != 'api.scryfall.com':
        return

    global _LAST_SCRYFALL_REQUEST_AT
    with _SCRYFALL_LOCK:
        elapsed = time.monotonic() - _LAST_SCRYFALL_REQUEST_AT
        if elapsed < SCRYFALL_MIN_INTERVAL_SECONDS:
            time.sleep(SCRYFALL_MIN_INTERVAL_SECONDS - elapsed)
        _LAST_SCRYFALL_REQUEST_AT = time.monotonic()


def _retry_delay_seconds(error, attempt):
    retry_after = error.headers.get('Retry-After') if error.headers else None
    if retry_after:
        try:
            return min(float(retry_after), HTTP_BACKOFF_MAX_SECONDS)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                return min(max(retry_at.timestamp() - time.time(), 0), HTTP_BACKOFF_MAX_SECONDS)
            except (TypeError, ValueError):
                pass
    return min(HTTP_BACKOFF_SECONDS * (2 ** attempt), HTTP_BACKOFF_MAX_SECONDS)
