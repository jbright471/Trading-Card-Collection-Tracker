"""Wishlist parsing & deal detection."""
import json
import os
import time
from datetime import datetime

from tcg.config import (
    REQUEST_DELAY,
    WISHLIST_ALERTED_FILE,
    WISHLIST_CACHE_FILE,
    WISHLIST_COOLDOWN_DAYS,
    WISHLIST_FILE,
)
from tcg.sources import get_mtg_data, get_pokemon_data, get_yugioh_data


def parse_wishlist_entry(line):
    """Parse one wishlist.txt line. Returns dict or None if invalid/comment."""
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    game = 'MTG'
    if line.upper().startswith('[YGO]'):
        game = 'YGO'
        line = line[5:].strip()
    elif line.upper().startswith('[PKM]'):
        game = 'PKM'
        line = line[5:].strip()
    if '|' not in line:
        return None
    card_part, target_part = line.split('|', 1)
    card_line = card_part.strip()
    target_str = target_part.strip().replace('$', '').strip()
    operator = '<'
    for op in ('<=', '>=', '<', '>'):
        if target_str.startswith(op):
            operator = op
            target_str = target_str[len(op):].strip()
            break
    try:
        return {
            'card_line': card_line,
            'game': game,
            'target_price': float(target_str),
            'operator': operator,
        }
    except ValueError:
        return None


def is_deal(price, op, target):
    """True iff `price` satisfies `op target`. Operators: <, <=, >, >=."""
    if op == '<':
        return price < target
    if op == '<=':
        return price <= target
    if op == '>':
        return price > target
    if op == '>=':
        return price >= target
    return False


def should_send_alert(card_key, alerted, cooldown_days=WISHLIST_COOLDOWN_DAYS):
    """True if card_key has never been alerted or cooldown has elapsed."""
    if card_key not in alerted:
        return True
    try:
        last = datetime.strptime(alerted[card_key], '%Y-%m-%d')
        return (datetime.now() - last).days >= cooldown_days
    except (ValueError, TypeError):
        return True


def _price_label(operator, target):
    return f"{operator} {target:.2f}"


def _save_wishlist_cache(items):
    payload = {
        'last_updated': datetime.now().strftime('%Y-%m-%d'),
        'items': items,
    }
    try:
        with open(WISHLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f"Updated {WISHLIST_CACHE_FILE}")
    except OSError as e:
        print(f"Error saving wishlist cache: {e}")


def process_wishlist():
    """Fetch prices for all wishlist entries, return list of deal dicts."""
    if not os.path.exists(WISHLIST_FILE):
        return []

    alerted = {}
    if os.path.exists(WISHLIST_ALERTED_FILE):
        try:
            with open(WISHLIST_ALERTED_FILE) as f:
                alerted = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: could not read {WISHLIST_ALERTED_FILE}: {e}")

    with open(WISHLIST_FILE, encoding='utf-8') as f:
        entries = [entry for entry in (parse_wishlist_entry(line) for line in f) if entry]

    if not entries:
        return []

    print(f"Checking {len(entries)} wishlist card(s)...")
    today = datetime.now().strftime('%Y-%m-%d')
    fetchers = {'MTG': get_mtg_data, 'YGO': get_yugioh_data, 'PKM': get_pokemon_data}
    wishlist_items = []
    cache_items = []
    new_alerted = dict(alerted)

    for entry in entries:
        data = fetchers[entry['game']](entry['card_line'])
        if not data:
            print(f"[Wishlist] Skipped (No data): {entry['card_line']}")
            cache_items.append({
                'game': entry['game'],
                'card_line': entry['card_line'],
                'name': entry['card_line'],
                'target_price': entry['target_price'],
                'target_label': _price_label(entry['operator'], entry['target_price']),
                'operator': entry['operator'],
                'current_price': None,
                'set': '',
                'image': '',
                'uri': '#',
                'is_deal': False,
            })
            time.sleep(REQUEST_DELAY)
            continue

        current = 'N/A'
        if data['price'] != 'N/A':
            try:
                current = float(data['price'])
            except ValueError:
                pass

        target, op = entry['target_price'], entry['operator']
        deal = False
        savings = 0.0
        if current != 'N/A':
            deal = is_deal(current, op, target)
            savings = round(abs(target - current), 2)
            extra = f" — SNIPER DEAL! Save ${savings:.2f}" if deal else ""
            print(f"[Wishlist] {data['name']}: ${current:.2f} vs target {op}${target:.2f}{extra}")
        else:
            print(f"[Wishlist] {data['name']}: N/A vs target {op}${target:.2f}")

        card_key = f"wishlist|{entry['game']}|{entry['card_line']}"
        cache_items.append({
            'game': entry['game'],
            'card_line': entry['card_line'],
            'name': data.get('name') or entry['card_line'],
            'target_price': target,
            'target_label': _price_label(op, target),
            'operator': op,
            'current_price': current if current != 'N/A' else None,
            'set': data.get('set', ''),
            'image': data.get('image', ''),
            'uri': data.get('uri', '#'),
            'is_deal': deal,
        })
        wishlist_items.append({
            'data': data,
            'current_price': current,
            'target_price': target,
            'operator': op,
            'savings': savings,
            'is_deal': deal,
            'needs_alert': should_send_alert(card_key, alerted) if deal else False,
        })
        if deal:
            new_alerted[card_key] = today
        time.sleep(REQUEST_DELAY)

    _save_wishlist_cache(cache_items)

    try:
        with open(WISHLIST_ALERTED_FILE, 'w') as f:
            json.dump(new_alerted, f, indent=2)
    except OSError as e:
        print(f"Error saving wishlist alert log: {e}")
    return wishlist_items
