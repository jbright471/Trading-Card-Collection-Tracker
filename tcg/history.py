"""Historical totals, per-card price history, mover detection, value graph."""
import csv
import json
import os
import re
from datetime import datetime

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from tcg.config import (
    ALERT_THRESHOLD_PERCENT,
    CARD_HISTORY_FILE,
    GRAPH_FILE,
    HISTORY_FILE,
    HISTORY_RETENTION_DAYS,
)
from tcg.notify import send_value_alert


def update_history_and_graph(total_value):
    today = datetime.now().strftime('%Y-%m-%d')
    history = []
    previous_value = 0.0

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, newline='') as f:
            history = [row for row in csv.reader(f) if row]
            for row in reversed(history):
                if row[0] != today:
                    try:
                        previous_value = float(row[1])
                        break
                    except (ValueError, IndexError):
                        pass

    updated = False
    for row in history:
        if row and row[0] == today:
            row[1] = f"{total_value:.2f}"
            updated = True
            break
    if not updated:
        history.append([today, f"{total_value:.2f}"])

    history.sort(key=lambda x: x[0])

    with open(HISTORY_FILE, 'w', newline='') as f:
        csv.writer(f).writerows(history)

    if history:
        dates = [datetime.strptime(row[0], '%Y-%m-%d') for row in history]
        values = [float(row[1]) for row in history]

        plt.figure(figsize=(10, 5))
        plt.plot(dates, values, marker='o', linestyle='-', color='#6c5ce7', linewidth=2)
        plt.title('Total Collection Value', fontsize=14)
        plt.xlabel('Date')
        plt.ylabel('Value (USD)')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        plt.gcf().autofmt_xdate()
        plt.savefig(GRAPH_FILE, bbox_inches='tight')
        plt.close()

    if previous_value > 0:
        percent_change = ((total_value - previous_value) / previous_value) * 100
        if percent_change >= ALERT_THRESHOLD_PERCENT:
            send_value_alert(total_value, percent_change)


def save_card_history(date, card_prices):
    """Append today's per-card prices to a rolling history file."""
    if not card_prices:
        return
    history = {}
    if os.path.exists(CARD_HISTORY_FILE):
        try:
            with open(CARD_HISTORY_FILE) as f:
                history = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: could not read {CARD_HISTORY_FILE}: {e}")
    history[date] = card_prices
    if len(history) > HISTORY_RETENTION_DAYS:
        for old_date in sorted(history.keys())[:-HISTORY_RETENTION_DAYS]:
            del history[old_date]
    with open(CARD_HISTORY_FILE, 'w') as f:
        json.dump(history, f)


def load_card_history():
    if not os.path.exists(CARD_HISTORY_FILE):
        return {}
    try:
        with open(CARD_HISTORY_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: could not read {CARD_HISTORY_FILE}: {e}")
        return {}


def load_value_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, newline='') as f:
            return [[row[0], float(row[1])] for row in csv.reader(f) if row]
    except (OSError, ValueError, IndexError) as e:
        print(f"Warning: could not read {HISTORY_FILE}: {e}")
        return []


def compute_today_delta(value_history):
    """Return (dollar_delta, pct_delta) vs previous day, or (None, None)."""
    if len(value_history) < 2:
        return None, None
    today_val = value_history[-1][1]
    yesterday_val = value_history[-2][1]
    if yesterday_val == 0:
        return None, None
    dollar_delta = today_val - yesterday_val
    pct_delta = (dollar_delta / yesterday_val) * 100
    return dollar_delta, pct_delta


def compute_gainers_losers(card_history, all_items, top_n=5):
    """Return (gainers, losers) — each a list of dicts with card display info + % change.

    all_items is the list of result dicts from process_file (provides images, game, set, name).
    """
    sorted_dates = sorted(card_history.keys())
    if len(sorted_dates) < 2:
        return [], []

    today_key = sorted_dates[-1]
    yesterday_key = sorted_dates[-2]
    today_prices = card_history[today_key]
    yesterday_prices = card_history[yesterday_key]

    # Build lookup: card_key → item data
    item_lookup = {item['card_key']: item for item in all_items}

    movers = []
    for key, price_str in today_prices.items():
        if key not in yesterday_prices:
            continue
        try:
            today_p = float(price_str)
            yesterday_p = float(yesterday_prices[key])
        except (ValueError, TypeError):
            continue
        if yesterday_p == 0 or today_p == 0:
            continue
        pct = ((today_p - yesterday_p) / yesterday_p) * 100
        dollar = today_p - yesterday_p
        if abs(pct) < 0.05:
            continue
        item = item_lookup.get(key, {})
        data = item.get('data', {})
        name = data.get('name', key.split('|', 1)[-1])
        short_name = re.sub(r'\s*\(.*?\)', '', name).strip()
        if len(short_name) > 22:
            short_name = short_name[:20] + '\u2026'
        movers.append({
            'name': short_name,
            'full_name': name,
            'game': data.get('game', ''),
            'set': data.get('set', ''),
            'image': data.get('image', ''),
            'price': today_p,
            'pct': pct,
            'dollar': dollar,
        })

    movers.sort(key=lambda x: x['pct'], reverse=True)
    gainers = movers[:top_n]
    losers = sorted(movers, key=lambda x: x['pct'])[:top_n]
    return gainers, losers


def compute_daily_movers(card_history, display_names, top_n=3):
    """Return {date: [{name, delta}]} listing the top N price movers for each day."""
    sorted_dates = sorted(card_history.keys())
    movers = {}
    for i in range(1, len(sorted_dates)):
        today = sorted_dates[i]
        yesterday = sorted_dates[i - 1]
        today_prices = card_history[today]
        yesterday_prices = card_history[yesterday]
        deltas = []
        for key, price_str in today_prices.items():
            if key not in yesterday_prices:
                continue
            try:
                delta = float(price_str) - float(yesterday_prices[key])
            except (ValueError, TypeError):
                continue
            if abs(delta) < 0.01:
                continue
            raw_name = display_names.get(key, key.split('|', 1)[-1])
            short = re.sub(r'\s*\(.*?\)', '', raw_name).strip()
            short = re.sub(r'\s*#\S+', '', short).strip()
            short = re.sub(r'^\d+x\s+', '', short).strip()
            if len(short) > 24:
                short = short[:22] + '\u2026'
            sign = '+' if delta >= 0 else ''
            deltas.append({'name': short, 'delta': f'{sign}{delta:.2f}'})
        deltas.sort(key=lambda x: abs(float(x['delta'])), reverse=True)
        if deltas:
            movers[today] = deltas[:top_n]
    return movers
