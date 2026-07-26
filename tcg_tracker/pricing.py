import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from email.utils import parsedate_to_datetime

from .core import parse_collection_line, update_history
from .storage import entry_to_card

USER_AGENT = "MultiTCGTracker/1.0"
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_DELAY_SECONDS = float(
    os.environ.get("REQUEST_DELAY", os.environ.get("TCG_TRACKER_REQUEST_DELAY_SECONDS", "0.75"))
)
HTTP_MAX_RETRIES = int(os.environ.get("HTTP_MAX_RETRIES", "4"))
HTTP_BACKOFF_SECONDS = float(os.environ.get("HTTP_BACKOFF_SECONDS", "1.0"))
HTTP_BACKOFF_MAX_SECONDS = float(os.environ.get("HTTP_BACKOFF_MAX_SECONDS", "20.0"))
SCRYFALL_MIN_INTERVAL_SECONDS = float(os.environ.get("SCRYFALL_MIN_INTERVAL_SECONDS", "0.65"))
_SCRYFALL_LOCK = threading.Lock()
_LAST_SCRYFALL_REQUEST_AT = 0.0


def search_cards(game, query):
    game = str(game or "").upper()
    query = str(query or "").strip()
    if not query:
        return []

    if game == "MTG":
        return search_mtg(query)
    if game == "YGO":
        return search_ygo(query)
    if game == "PKM":
        return search_pokemon(query)
    raise ValueError(f"Unsupported game: {game}")


def refresh_collection(store, today=None):
    entries = store.read_entries()
    cards = []
    failures = []

    for entry in entries:
        try:
            card = fetch_entry(entry)
            cards.append(card)
        except Exception as exc:
            fallback = entry_to_card(entry)
            cards.append(fallback)
            failures.append({"game": entry.game, "name": entry.name, "error": str(exc)})
        time.sleep(REQUEST_DELAY_SECONDS)

    total_value = sum(card.get("value") or 0 for card in cards)
    history_result = update_history(
        store.history_path,
        total_value,
        today=today or date.today(),
        failed_cards=len(failures),
        total_cards=len(entries),
    )
    state = {
        "last_updated": (today or date.today()).isoformat(),
        "total_value": round(total_value, 2),
        "cards": cards,
        "failures": failures,
        "history_updated": history_result.updated,
        "history_note": history_result.reason,
    }
    store.save_state(state)
    return state


def refresh_wishlist(store, today=None):
    source_items = store.read_wishlist(limit=0)
    cache_items = []
    failures = []

    for item in source_items:
        cached_item = dict(item)
        try:
            entry = parse_collection_line(item["card_line"], item["game"])
            card = fetch_entry(entry)
            current_price = price_to_float(card.get("price"))
            cached_item.update(
                {
                    "name": card.get("name") or item["card_line"],
                    "set": card.get("set", ""),
                    "image": card.get("image", ""),
                    "uri": card.get("uri", "#"),
                    "current_price": current_price,
                    "is_deal": target_is_met(
                        current_price,
                        item.get("operator"),
                        item.get("target_price"),
                    ),
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "game": item["game"],
                    "name": item["card_line"],
                    "error": str(exc),
                }
            )

        cache_items.append(
            {
                "game": cached_item["game"],
                "card_line": cached_item["card_line"],
                "name": cached_item.get("name") or cached_item["card_line"],
                "target_price": cached_item.get("target_price"),
                "target_label": cached_item.get("target") or "",
                "operator": cached_item.get("operator") or "<",
                "current_price": cached_item.get("current_price"),
                "set": cached_item.get("set", ""),
                "image": cached_item.get("image", ""),
                "uri": cached_item.get("uri", "#"),
                "is_deal": bool(cached_item.get("is_deal")),
            }
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    if source_items:
        store.save_wishlist_cache(cache_items, today=today or date.today())
    return {"items": cache_items, "failures": failures}


def target_is_met(price, operator, target):
    if price is None or target is None:
        return False
    if operator == "<=":
        return price <= target
    if operator == ">":
        return price > target
    if operator == ">=":
        return price >= target
    return price < target


def fetch_entry(entry):
    if entry.game == "MTG":
        result = fetch_mtg(entry.name, entry.finish)
    elif entry.game == "YGO":
        result = fetch_ygo(entry.name)
    elif entry.game == "PKM":
        result = fetch_pokemon(entry.name)
    else:
        raise ValueError(f"Unsupported game: {entry.game}")

    value = price_to_float(result.get("price"))
    result.update(
        {
            "quantity": entry.quantity,
            "finish": entry.finish,
            "condition": entry.condition,
            "buy_price": entry.buy_price,
            "value": round(value * entry.quantity, 2) if value is not None else None,
            "profit_loss": _profit_loss(value, entry.quantity, entry.buy_price),
            "stale": False,
        }
    )
    return result


def search_mtg(query):
    url = "https://api.scryfall.com/cards/search?q=" + urllib.parse.quote(query)
    data = request_json(url)
    cards = data.get("data", [])[:20]
    return [scryfall_to_card(card) for card in cards]


def fetch_mtg(name, finish="regular"):
    url = "https://api.scryfall.com/cards/named?fuzzy=" + urllib.parse.quote(name)
    return scryfall_to_card(request_json(url), finish=finish)


def scryfall_to_card(data, finish="regular"):
    prices = data.get("prices", {})
    price = prices.get("usd_foil") if finish == "foil" else prices.get("usd")
    price = price or prices.get("usd") or prices.get("usd_foil")
    image = ""
    if data.get("image_uris"):
        image = data["image_uris"].get("normal", "")
    elif data.get("card_faces"):
        image = data["card_faces"][0].get("image_uris", {}).get("normal", "")

    name = data.get("flavor_name") or data.get("name", "")
    collector_number = data.get("collector_number")
    card_line = f"{name} # {collector_number}" if collector_number else name
    return {
        "game": "MTG",
        "name": name,
        "set": data.get("set_name", ""),
        "set_code": data.get("set", ""),
        "price": price,
        "image": image,
        "uri": data.get("scryfall_uri", "#"),
        "card_line": card_line,
        "finishes": data.get("finishes", ["regular"]),
    }


def search_ygo(query):
    url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?fname=" + urllib.parse.quote(query)
    data = request_json(url)
    return [ygo_to_card(card) for card in data.get("data", [])[:20]]


def fetch_ygo(name):
    url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?name=" + urllib.parse.quote(name)
    return ygo_to_card(request_json(url).get("data", [])[0])


def ygo_to_card(card):
    prices = card.get("card_prices") or [{}]
    images = card.get("card_images") or [{}]
    sets = card.get("card_sets") or [{}]
    name = card.get("name", "")
    return {
        "game": "YGO",
        "name": name,
        "set": sets[0].get("set_name", "Yu-Gi-Oh!"),
        "price": prices[0].get("tcgplayer_price"),
        "image": images[0].get("image_url", ""),
        "uri": "https://db.ygoprodeck.com/card/?search=" + urllib.parse.quote(name),
        "card_line": name,
        "finishes": ["regular", "foil"],
    }


def search_pokemon(query):
    url = "https://api.tcgdex.net/v2/en/cards?name=" + urllib.parse.quote(query)
    data = request_json(url)
    return [pokemon_to_card(card) for card in data[:20]]


def fetch_pokemon(name):
    card_id = ""
    if "#" in name:
        card_id = name.rsplit("#", 1)[1].strip()
    if card_id:
        url = "https://api.tcgdex.net/v2/en/cards/" + urllib.parse.quote(
            card_id,
            safe="-.",
        )
        return pokemon_to_card(request_json(url))

    results = search_pokemon(name)
    if not results:
        raise ValueError(f"Pokemon card not found: {name}")
    first_card = results[0]
    if "#" not in first_card.get("card_line", ""):
        return first_card
    card_id = first_card["card_line"].rsplit("#", 1)[1].strip()
    url = "https://api.tcgdex.net/v2/en/cards/" + urllib.parse.quote(
        card_id,
        safe="-.",
    )
    return pokemon_to_card(request_json(url))


def pokemon_to_card(card):
    image = card.get("image", "")
    if image and not image.endswith("/high.png"):
        image = f"{image}/high.png"
    name = card.get("name", "")
    card_id = card.get("id", "")
    return {
        "game": "PKM",
        "name": name,
        "set": card.get("set", {}).get("name", ""),
        "price": pokemon_price(card),
        "image": image,
        "uri": f"https://tcgdex.dev/en/cards/{card_id}" if card_id else "#",
        "card_line": f"{name} # {card_id}" if card_id else name,
        "finishes": ["regular", "foil"],
    }


def pokemon_price(card):
    pricing = card.get("pricing") or {}
    tcgplayer = pricing.get("tcgplayer") or {}
    for variant in ("normal", "holofoil", "reverseHolofoil"):
        values = tcgplayer.get(variant) or {}
        price = (
            values.get("marketPrice")
            or values.get("market")
            or values.get("midPrice")
            or values.get("mid")
        )
        if price is not None:
            return price

    cardmarket = pricing.get("cardmarket") or {}
    return cardmarket.get("avg") or cardmarket.get("trend")


def request_json(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("Only HTTPS API URLs are allowed")

    last_error = None
    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            _pace_scryfall_request(url)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(  # nosec B310
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt >= HTTP_MAX_RETRIES:
                raise
            time.sleep(_retry_delay_seconds(exc, attempt))

    raise last_error


def _pace_scryfall_request(url):
    if urllib.parse.urlparse(url).netloc.lower() != "api.scryfall.com":
        return

    global _LAST_SCRYFALL_REQUEST_AT
    with _SCRYFALL_LOCK:
        elapsed = time.monotonic() - _LAST_SCRYFALL_REQUEST_AT
        if elapsed < SCRYFALL_MIN_INTERVAL_SECONDS:
            time.sleep(SCRYFALL_MIN_INTERVAL_SECONDS - elapsed)
        _LAST_SCRYFALL_REQUEST_AT = time.monotonic()


def _retry_delay_seconds(error, attempt):
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if retry_after:
        try:
            return min(float(retry_after), HTTP_BACKOFF_MAX_SECONDS)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                return min(max(retry_at.timestamp() - time.time(), 0), HTTP_BACKOFF_MAX_SECONDS)
            except (TypeError, ValueError):
                pass
    return min(HTTP_BACKOFF_SECONDS * (2**attempt), HTTP_BACKOFF_MAX_SECONDS)


def price_to_float(price):
    if price in (None, "", "N/A"):
        return None
    try:
        return float(price)
    except (TypeError, ValueError):
        return None


def _profit_loss(unit_price, quantity, buy_price):
    if unit_price is None or buy_price is None:
        return None
    return round((unit_price - buy_price) * quantity, 2)
