"""Collection-list parsing & per-card processing."""
import re
import time

from tcg.config import REQUEST_DELAY
from tcg.sources import GAME_FETCHERS, get_mtg_data


def dedupe_lines(lines):
    """In-memory dedupe preserving first occurrence; does not touch the source file."""
    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            out.append(stripped)
    return out


def detect_game(line, default='MTG'):
    """Strip optional [MTG]/[YGO]/[PKM] prefix; return (game, remainder)."""
    upper = line.upper()
    for tag in ('MTG', 'YGO', 'PKM'):
        if upper.startswith(f'[{tag}]'):
            return tag, line[5:].strip()
    return default, line


def parse_card_line(card):
    """Parse '2x Card Name (Foil) #042 | 3.50' → (qty, clean_card_line, is_foil, buy_price)."""
    quantity = 1
    bought_price = None

    if '|' in card:
        parts = card.split('|')
        card = parts[0].strip()
        try:
            bought_price = float(parts[1].strip())
        except ValueError:
            pass

    clean_card_line = card
    qty_match = re.match(r'^(\d+)x\s+(.*)', card)
    if qty_match:
        quantity = int(qty_match.group(1))
        clean_card_line = qty_match.group(2).strip()

    # Match any (…foil…) group: (Foil), (Surge Foil), (Borderless Foil), (Foil Etched), etc.
    is_foil = bool(re.search(r'\([^)]*\bfoil\b[^)]*\)', clean_card_line, re.IGNORECASE))
    if is_foil:
        clean_card_line = re.sub(r'\s*\([^)]*\bfoil\b[^)]*\)', '', clean_card_line, flags=re.IGNORECASE).strip()
        clean_card_line = re.sub(r'\s+', ' ', clean_card_line)

    return quantity, clean_card_line, is_foil, bought_price


def process_file(filename, default_game='MTG', last_run_prices=None, last_run_data=None):
    """Process a card list. Each line may be tagged [MTG]/[YGO]/[PKM]; default applies otherwise."""
    last_run_prices = last_run_prices or {}
    last_run_data = last_run_data or {}

    try:
        with open(filename, encoding='utf-8') as f:
            raw_lines = [
                line for line in f if line.strip() and not line.lstrip().startswith('#')
            ]
    except FileNotFoundError:
        print(f"Note: {filename} not found. Skipping.")
        return [], set()

    cards = dedupe_lines(raw_lines)
    results = []
    attempted_keys = set()
    print(f"Fetching prices for {len(cards)} card(s) from {filename}...")

    for raw_card in cards:
        game_name, card = detect_game(raw_card, default_game)
        fetch_func = GAME_FETCHERS.get(game_name, get_mtg_data)
        quantity, clean_card_line, is_foil, bought_price = parse_card_line(card)

        card_key = f"{game_name}|{card}"
        attempted_keys.add(card_key)

        data = fetch_func(clean_card_line)
        if data:
            unit_price_str = data['price']
            total_price_str = unit_price_str
            profit_loss = None
            trend_diff = None
            sort_val = -1.0

            if unit_price_str != 'N/A':
                try:
                    unit_price = float(unit_price_str)
                    total_price = unit_price * quantity
                    total_price_str = f"{total_price:.2f}"
                    sort_val = float(total_price_str)

                    if bought_price is not None:
                        profit_loss = total_price - (bought_price * quantity)

                    if card_key in last_run_prices:
                        try:
                            trend_diff = sort_val - float(last_run_prices[card_key])
                        except ValueError:
                            pass
                except ValueError:
                    pass

            results.append({
                'data': data,
                'quantity': quantity,
                'price_str': total_price_str,
                'profit_loss': profit_loss,
                'sort_val': sort_val,
                'is_foil': is_foil,
                'trend_diff': trend_diff,
                'card_key': card_key,
            })
            print(f"[{game_name}] Fetched: {data['name']} - ${total_price_str}")
        else:
            cached = _fallback_from_cache(card_key, clean_card_line, game_name, quantity, is_foil,
                                          last_run_prices, last_run_data)
            if cached:
                results.append(cached)
                source = 'cached' if 'data' in cached and cached['data']['set'] != 'Cached' else 'cached price only'
                print(f"[{game_name}] Fetch failed ({source}): {cached['data']['name']} - ${cached['price_str']}")
            else:
                print(f"[{game_name}] Skipped (no cache): {card}")
        time.sleep(REQUEST_DELAY)
    return results, attempted_keys


def _fallback_from_cache(card_key, clean_card_line, game_name, quantity, is_foil,
                          last_run_prices, last_run_data):
    """Return a result dict reconstituted from previous-run cache, or None."""
    if card_key in last_run_data:
        cached = last_run_data[card_key]
        return {**cached, 'trend_diff': None, 'stale': True}
    if card_key in last_run_prices:
        try:
            cached_price = float(last_run_prices[card_key])
        except ValueError:
            return None
        return {
            'data': {'game': game_name, 'name': clean_card_line, 'set': 'Cached',
                     'price': last_run_prices[card_key], 'image': '', 'uri': '#'},
            'quantity': quantity,
            'price_str': last_run_prices[card_key],
            'profit_loss': None,
            'sort_val': cached_price,
            'is_foil': is_foil,
            'trend_diff': None,
            'card_key': card_key,
            'stale': True,
        }
    return None
