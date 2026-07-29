"""Per-game card data fetchers — MTG (Scryfall), YGO (YGOPRODeck), PKM (TCGdex)."""
import json
import re
import urllib.error
import urllib.parse

from tcg.http import get_json


# --- Magic: The Gathering (Scryfall) ---
def get_mtg_data(card_line, is_foil=None):
    finish = "etched" if "etched" in card_line.lower() else (
        "foil" if is_foil or re.search(r"\([^)]*foil[^)]*\)", card_line, re.IGNORECASE) else "regular"
    )
    match = re.search(r'^(.*?)\s+#\s*(\S+)$', card_line)
    queries = []
    clean_name = card_line

    if match:
        name_part = match.group(1).strip()
        number_part = match.group(2).strip()
        clean_name = re.sub(r'\s*\(.*?\)', '', name_part).strip()
        number_stripped = number_part.lstrip('0') or "0"

        queries.append(f'name:"{clean_name}" cn:"{number_part}"')
        queries.append(f'name:"{clean_name}" cn:"{number_stripped}"')
        queries.append(f'!"{clean_name}"')
        queries.append(f'"{clean_name}"')
    elif ' - ' in card_line:
        parts = card_line.split(' - ')
        clean_name = parts[0].strip()
        set_info = parts[1].strip()
        queries.append(f'name:"{clean_name}" s:"{set_info}"')
        queries.append(f'name:"{clean_name}"')
        queries.append(f'"{clean_name}"')
    else:
        queries.append(f'!"{clean_name}"')
        queries.append(f'"{clean_name}"')

    for q in queries:
        url = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote(q)}"
        try:
            data = get_json(url)
            if data.get('total_cards', 0) > 0:
                return _parse_scryfall(data['data'][0], clean_name, finish)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
            continue

    # Fuzzy fallback — strip collector number
    try:
        fuzzy_name = re.sub(r'\s*#\s*\d+', '', clean_name).strip()
        url = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(fuzzy_name)}"
        return _parse_scryfall(get_json(url), clean_name, finish)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"[MTG] Error fetching {card_line}: {e}")
        return None


def _parse_scryfall(data, default_name, finish="regular"):
    prices = data.get('prices', {})
    price_key = {'regular': 'usd', 'foil': 'usd_foil', 'etched': 'usd_etched'}.get(finish, 'usd')
    price = prices.get(price_key) or prices.get('usd') or prices.get('usd_foil') or prices.get('usd_etched') or 'N/A'

    name = data.get('flavor_name') or data.get('name') or default_name

    image_url = ""
    if 'image_uris' in data:
        image_url = data['image_uris'].get('normal', '')
    elif 'card_faces' in data and data['card_faces']:
        image_url = data['card_faces'][0].get('image_uris', {}).get('normal', '')

    return {
        'game': 'MTG',
        'name': name,
        'set': data.get('set_name', 'Unknown'),
        'price': price,
        'image': image_url,
        'uri': data.get('scryfall_uri', '#'),
    }


# --- Yu-Gi-Oh! (YGOPRODeck) ---
def get_yugioh_data(card_line):
    clean_name = re.sub(r'\s*\(.*?\)', '', card_line).strip()
    url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={urllib.parse.quote(clean_name)}"
    try:
        data = get_json(url)
        if data.get('data'):
            return _parse_ygo(data['data'][0], clean_name)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return _get_yugioh_fuzzy(clean_name)
        print(f"[YGO] Error fetching {card_line}: HTTP {e.code}")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"[YGO] Error fetching {card_line}: {e}")
    return None


def _get_yugioh_fuzzy(clean_name):
    url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?fname={urllib.parse.quote(clean_name)}"
    try:
        data = get_json(url)
        if data.get('data'):
            return _parse_ygo(data['data'][0], clean_name)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None
    return None


def _parse_ygo(card_data, default_name):
    price = 'N/A'
    if card_data.get('card_prices'):
        price = card_data['card_prices'][0].get('tcgplayer_price', 'N/A')

    image_url = ""
    if card_data.get('card_images'):
        image_url = card_data['card_images'][0].get('image_url', '')

    set_name = "Yu-Gi-Oh!"
    if card_data.get('card_sets'):
        set_name = card_data['card_sets'][0].get('set_name', 'Unknown Set')

    name = card_data.get('name') or default_name
    return {
        'game': 'YGO',
        'name': name,
        'set': set_name,
        'price': str(price),
        'image': image_url,
        'uri': f"https://db.ygoprodeck.com/card/?search={urllib.parse.quote(name)}",
    }


# --- Pokémon (TCGdex) ---
def get_pokemon_data(card_line):
    """Format: 'Card Name #SetID-LocalID' (e.g., 'Dragonite EX #xy12-106')."""
    match = re.search(r'^(.*?)\s+#(\S+)$', card_line.strip())
    if not match:
        print(f"[PKM] Invalid format: '{card_line}' (expected: Name #SetID-LocalID)")
        return None

    card_name = match.group(1).strip()
    card_api_id = match.group(2).strip()

    url = f"https://api.tcgdex.net/v2/en/cards/{urllib.parse.quote(card_api_id, safe='-.')}"
    try:
        data = get_json(url)
    except urllib.error.HTTPError as e:
        print(f"[PKM] Error fetching {card_api_id}: HTTP {e.code}")
        return None
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"[PKM] Error fetching {card_api_id}: {e}")
        return None

    price = 'N/A'
    pricing = data.get('pricing') or {}
    tcg = pricing.get('tcgplayer') or {}
    if tcg:
        for variant in ('normal', 'holofoil', 'reverseHolofoil'):
            v = tcg.get(variant) or {}
            val = v.get('marketPrice') or v.get('market') or v.get('midPrice') or v.get('mid')
            if val:
                price = str(val)
                break
    if price == 'N/A':
        cm = pricing.get('cardmarket') or {}
        val = cm.get('avg') or cm.get('trend')
        if val:
            price = str(val)

    image_url = data.get('image', '')
    if image_url:
        image_url = f"{image_url}/high.png"

    set_info = data.get('set') or {}
    return {
        'game': 'PKM',
        'name': data.get('name') or card_name,
        'set': set_info.get('name', card_api_id.split('-')[0]),
        'price': price,
        'image': image_url,
        'uri': f"https://tcgdex.dev/en/cards/{card_api_id}",
    }


GAME_FETCHERS = {
    'MTG': get_mtg_data,
    'YGO': get_yugioh_data,
    'PKM': get_pokemon_data,
}
