from collections import defaultdict
from statistics import median


def portfolio_breakdowns(cards):
    priced = [
        card
        for card in cards
        if card.get("value") is not None
        and str(card.get("currency") or "USD").upper() == "USD"
    ]
    total_value = round(sum(card.get("value") or 0 for card in priced), 2)
    total_cost = round(
        sum(
            (card.get("buy_price") or 0) * (card.get("quantity") or 1)
            for card in cards
            if card.get("buy_price") is not None
        ),
        2,
    )

    dimensions = {}
    for key in ("game", "set", "finish", "condition"):
        groups = defaultdict(lambda: {"value": 0.0, "cards": 0})
        for card in cards:
            label = str(card.get(key) or "Unknown")
            if str(card.get("currency") or "USD").upper() == "USD":
                groups[label]["value"] += card.get("value") or 0
            groups[label]["cards"] += card.get("quantity") or 1
        rows = [
            {
                "label": label,
                "value": round(data["value"], 2),
                "cards": data["cards"],
                "pct": round((data["value"] / total_value) * 100, 1) if total_value else 0,
            }
            for label, data in groups.items()
        ]
        dimensions[key] = sorted(rows, key=lambda row: row["value"], reverse=True)

    top_cards = sorted(priced, key=lambda card: card.get("value") or 0, reverse=True)[:5]
    top_three_value = sum(card.get("value") or 0 for card in top_cards[:3])
    concentration = round((top_three_value / total_value) * 100, 1) if total_value else 0
    foreign_totals = defaultdict(float)
    for card in cards:
        currency = str(card.get("currency") or "USD").upper()
        if currency != "USD" and card.get("value") is not None:
            foreign_totals[currency] += card.get("value") or 0
    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "unrealized_profit": round(total_value - total_cost, 2),
        "dimensions": dimensions,
        "top_cards": top_cards,
        "top_three_pct": concentration,
        "foreign_totals": {
            currency: round(value, 2) for currency, value in sorted(foreign_totals.items())
        },
    }


def compute_movers(card_history, cards, top_n=4):
    dates = sorted(card_history)
    if len(dates) < 2:
        return {"from": None, "to": None, "gainers": [], "losers": []}

    previous, current = dates[-2], dates[-1]
    before = card_history.get(previous, {})
    after = card_history.get(current, {})
    lookup = {}
    for card in cards:
        for key in _card_aliases(card):
            lookup[key] = card

    movers = []
    for key, current_price in after.items():
        if key not in before:
            continue
        try:
            current_value = float(current_price)
            previous_value = float(before[key])
        except (TypeError, ValueError):
            continue
        if previous_value <= 0 or current_value <= 0:
            continue
        delta = round(current_value - previous_value, 2)
        pct = round((delta / previous_value) * 100, 1)
        if abs(delta) < 0.01:
            continue
        card = lookup.get(key, {})
        movers.append(
            {
                "card_id": card.get("card_id", ""),
                "name": card.get("name") or key.split("|", 1)[-1],
                "game": card.get("game", ""),
                "image": card.get("image", ""),
                "price": current_value,
                "delta": delta,
                "pct": pct,
            }
        )

    gainers = sorted(movers, key=lambda row: row["pct"], reverse=True)[:top_n]
    losers = sorted(movers, key=lambda row: row["pct"])[:top_n]
    return {"from": previous, "to": current, "gainers": gainers, "losers": losers}


def transaction_summary(transactions):
    sales = [item for item in transactions if item.get("type") == "sale"]
    purchases = [item for item in transactions if item.get("type") == "purchase"]
    return {
        "sales_count": len(sales),
        "purchase_count": len(purchases),
        "sales_net": round(sum(item.get("net_amount") or 0 for item in sales), 2),
        "realized_profit": round(sum(item.get("realized_profit") or 0 for item in sales), 2),
        "recorded_cost": round(sum(item.get("total_amount") or 0 for item in purchases), 2),
    }


def data_health(state, history, refresh_status=None):
    cards = state.get("cards", [])
    stale = [card for card in cards if card.get("stale")]
    unpriced = [card for card in cards if card.get("value") is None]
    attention = []
    seen_attention = set()
    for card in stale + unpriced:
        key = card.get("card_id") or f"{card.get('game')}|{card.get('name')}"
        if key not in seen_attention:
            seen_attention.add(key)
            attention.append(card)
    sources = defaultdict(int)
    currencies = defaultdict(int)
    for card in cards:
        sources[card.get("source") or "Unknown"] += 1
        currencies[card.get("currency") or "Unknown"] += 1

    anomalies = []
    values = [row.get("value") for row in history if isinstance(row.get("value"), (int, float))]
    baseline = median(values) if values else 0
    for index, row in enumerate(history):
        value = row.get("value")
        if not isinstance(value, (int, float)) or value <= 0:
            continue
        previous = history[index - 1].get("value") if index else None
        pct = ((value - previous) / previous) * 100 if previous else 0
        baseline_gap = abs(value - baseline) / baseline * 100 if baseline else 0
        if (previous and abs(pct) >= 35 and abs(value - previous) >= 25) or baseline_gap >= 70:
            anomalies.append(
                {
                    "date": row.get("date"),
                    "value": value,
                    "change_pct": round(pct, 1),
                }
            )

    return {
        "stale_cards": stale,
        "unpriced_cards": unpriced,
        "attention_cards": attention,
        "failures": state.get("failures", []),
        "sources": dict(sorted(sources.items())),
        "currencies": dict(sorted(currencies.items())),
        "anomalies": anomalies,
        "refresh": refresh_status or {},
    }


def _card_aliases(card):
    aliases = {
        card.get("card_id"),
        card.get("card_key"),
        f"{card.get('game', '')}|{card.get('source_line', '')}",
    }
    return {alias for alias in aliases if alias}
