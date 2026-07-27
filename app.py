import os

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from tcg_tracker.pricing import refresh_collection, refresh_wishlist, search_cards
from tcg_tracker.storage import TrackerStore


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATA_DIR=os.environ.get("TCG_TRACKER_DATA_DIR", "."),
        COLLECTION_FILE=os.environ.get("TCG_TRACKER_COLLECTION_FILE"),
        DISABLE_NETWORK=os.environ.get("TCG_TRACKER_DISABLE_NETWORK", "").lower()
        in {"1", "true", "yes"},
    )
    if config:
        app.config.update(config)

    store = TrackerStore(app.config["DATA_DIR"], app.config.get("COLLECTION_FILE"))

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", **dashboard_context(store))

    @app.get("/add")
    def add_card_page():
        return render_template("add.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "data": store.data_status()})

    @app.get("/api/status")
    def api_status():
        return jsonify(store.data_status())

    @app.get("/download/excel")
    def download_excel():
        if not store.excel_path.exists():
            abort(404)
        return send_file(store.excel_path, as_attachment=True)

    @app.get("/api/search/<game>")
    def api_search(game):
        if app.config["DISABLE_NETWORK"]:
            return jsonify([])

        query = request.args.get("q", "")
        try:
            return jsonify(search_cards(game, query))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        except Exception as exc:
            return jsonify({"error": f"Search failed: {exc}"}), 502

    @app.post("/api/add-card")
    def api_add_card():
        payload = request.get_json(silent=True) or {}
        try:
            result = store.add_card(
                payload.get("game"),
                payload.get("card_line"),
                payload.get("quantity", 1),
                payload.get("finish", "regular"),
                payload.get("buy_price", ""),
                payload.get("condition", ""),
            )
            return jsonify(result)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/refresh")
    def api_refresh():
        if app.config["DISABLE_NETWORK"]:
            return jsonify({"error": "Network refresh is disabled"}), 503

        try:
            state = refresh_collection(store)
            wishlist_state = refresh_wishlist(store)
            return jsonify(
                {
                    "status": "refreshed",
                    "total_value": state.get("total_value"),
                    "failures": len(state.get("failures", [])),
                    "history_updated": state.get("history_updated"),
                    "history_note": state.get("history_note"),
                    "wishlist_updated": len(wishlist_state.get("items", [])),
                    "wishlist_failures": len(wishlist_state.get("failures", [])),
                }
            )
        except Exception as exc:
            return jsonify({"error": f"Refresh failed: {exc}"}), 500

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    return app


def dashboard_context(store):
    state = store.load_state()
    cards = sorted(
        state.get("cards", []),
        key=lambda card: card.get("value") or -1,
        reverse=True,
    )
    total_value = sum(card.get("value") or 0 for card in cards)
    profit_loss = sum(
        card.get("profit_loss") or 0 for card in cards if card.get("profit_loss") is not None
    )
    priced_cards = sum(1 for card in cards if card.get("value") is not None)
    history = store.read_history()
    status = store.data_status()
    wishlist = store.read_wishlist()

    return {
        "cards": cards,
        "history": history,
        "status": status,
        "total_value": round(total_value, 2),
        "profit_loss": round(profit_loss, 2),
        "card_count": sum(card.get("quantity") or 1 for card in cards),
        "priced_cards": priced_cards,
        "wishlist": wishlist,
        "snapshot": dashboard_snapshot(cards, history, wishlist, status),
        "excel_available": store.excel_path.exists(),
    }


def dashboard_snapshot(cards, history, wishlist, status):
    return {
        "trend": history_trend(history),
        "top_card": top_card_snapshot(cards),
        "closest_wishlist": closest_wishlist_snapshot(wishlist),
        "freshness": freshness_snapshot(status),
    }


def history_trend(history):
    if len(history) < 2:
        return None

    current = history[-1].get("value")
    previous = history[-2].get("value")
    if current is None or previous in (None, 0):
        return None

    delta = round(current - previous, 2)
    pct = round((delta / previous) * 100, 1)
    return {
        "value": delta,
        "pct": pct,
        "class": "positive" if delta >= 0 else "negative",
        "label": "vs previous refresh",
    }


def top_card_snapshot(cards):
    for card in cards:
        if card.get("value") is not None:
            return {
                "name": card.get("name", "Unknown card"),
                "value": round(card.get("value") or 0, 2),
                "game": card.get("game", ""),
            }
    return None


def closest_wishlist_snapshot(wishlist):
    candidates = []
    for item in wishlist:
        current = item.get("current_price")
        target = item.get("target_price")
        if not isinstance(current, (int, float)) or not isinstance(target, (int, float)):
            continue

        operator = item.get("operator") or "<"
        wants_above = operator.startswith(">")
        gap = target - current if wants_above else current - target
        candidates.append((max(gap, 0), gap, wants_above, item))

    if not candidates:
        return None

    _, gap, wants_above, item = min(candidates, key=lambda candidate: candidate[0])
    if gap <= 0:
        label = "above target" if wants_above else "under target"
    else:
        label = "below target" if wants_above else "above target"

    return {
        "name": item.get("name") or item.get("card_line") or "Wishlist card",
        "amount": round(abs(gap), 2),
        "label": label,
        "class": "positive" if gap <= 0 else "negative",
    }


def freshness_snapshot(status):
    if status.get("state") == "ok":
        return "Current"
    if status.get("days_old") is not None:
        return f"{status['days_old']} days old"
    return "Needs refresh"


app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(
        host="0.0.0.0",  # nosec B104 - required for Docker/LAN access
        port=int(os.environ.get("PORT", "8084")),
        debug=debug,
        use_reloader=debug,
    )
