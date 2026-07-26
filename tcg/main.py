"""Top-level orchestration — load caches, fetch, render, save."""
import json
import os
from datetime import datetime

from tcg.cards import process_file
from tcg.config import COLLECTION_FILE, DATA_DIR, LAST_RUN_DATA, LAST_RUN_PRICES
from tcg.history import (
    compute_daily_movers,
    compute_gainers_losers,
    compute_today_delta,
    load_card_history,
    load_value_history,
    save_card_history,
    update_history_and_graph,
)
from tcg.notify import send_deal_alert
from tcg.report import generate_html_report, write_excel
from tcg.wishlist import process_wishlist


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error loading {path}: {e}")
        return {}


def _save_json(path, data, indent=4):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=indent)
        print(f"Updated {path}")
    except OSError as e:
        print(f"Error saving {path}: {e}")


def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    last_run_prices = _load_json(LAST_RUN_PRICES)
    last_run_data = _load_json(LAST_RUN_DATA)

    # Single collection file — lines may be tagged [MTG]/[YGO]/[PKM]; default is MTG.
    all_data, all_attempted_keys = process_file(
        COLLECTION_FILE, 'MTG', last_run_prices, last_run_data
    )

    total_collection_value = sum(item['sort_val'] for item in all_data if item['sort_val'] > 0)
    total_profit_loss = sum(item['profit_loss'] for item in all_data if item['profit_loss'] is not None)

    all_data.sort(key=lambda x: x['sort_val'], reverse=True)

    write_excel(all_data, total_collection_value, total_profit_loss)
    update_history_and_graph(total_collection_value)

    deals = process_wishlist()
    send_deal_alert(deals)

    today = datetime.now().strftime('%Y-%m-%d')
    # Only count non-stale items as "current" prices so history reflects actual fetched data
    current_prices = {
        item['card_key']: item['price_str']
        for item in all_data if item['price_str'] != 'N/A' and not item.get('stale')
    }
    display_names = {item['card_key']: item['data']['name'] for item in all_data}
    save_card_history(today, current_prices)
    card_history = load_card_history()
    movers_data = compute_daily_movers(card_history, display_names)
    value_history = load_value_history()
    dollar_delta, pct_delta = compute_today_delta(value_history)
    gainers, losers = compute_gainers_losers(card_history, all_data)

    generate_html_report(
        all_data, total_collection_value, total_profit_loss,
        value_history, movers_data, deals=deals,
        dollar_delta=dollar_delta, pct_delta=pct_delta,
        gainers=gainers, losers=losers,
    )

    # Persist caches — drop removed cards, keep last-known data for failed fetches
    merged_prices = {k: v for k, v in last_run_prices.items() if k in all_attempted_keys}
    merged_prices.update(current_prices)
    _save_json(LAST_RUN_PRICES, merged_prices)

    new_run_data = {
        item['card_key']: {
            'data': item['data'],
            'quantity': item['quantity'],
            'price_str': item['price_str'],
            'profit_loss': item['profit_loss'],
            'sort_val': item['sort_val'],
            'is_foil': item['is_foil'],
            'card_key': item['card_key'],
        }
        for item in all_data
        if not item.get('stale') and item['sort_val'] > 0
    }
    merged_run_data = {k: v for k, v in last_run_data.items() if k in all_attempted_keys}
    merged_run_data.update(new_run_data)
    _save_json(LAST_RUN_DATA, merged_run_data, indent=2)


if __name__ == '__main__':
    run()
