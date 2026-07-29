import hashlib
import hmac
import os
import secrets
from datetime import date

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from tcg.notify import send_test_alert
from tcg_tracker.analytics import (
    compute_movers,
    data_health,
    portfolio_breakdowns,
    transaction_summary,
)
from tcg_tracker.importer import parse_collection_csv
from tcg_tracker.pricing import search_cards
from tcg_tracker.refresh import RefreshManager
from tcg_tracker.storage import TrackerStore


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATA_DIR=os.environ.get("TCG_TRACKER_DATA_DIR", "."),
        COLLECTION_FILE=os.environ.get("TCG_TRACKER_COLLECTION_FILE"),
        DISABLE_NETWORK=os.environ.get("TCG_TRACKER_DISABLE_NETWORK", "").lower()
        in {"1", "true", "yes"},
        ACCESS_PIN=os.environ.get("TCG_TRACKER_PIN", ""),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    app.secret_key = os.environ.get("TCG_TRACKER_SECRET_KEY") or _default_secret(
        app.config.get("ACCESS_PIN")
    )

    store = TrackerStore(app.config["DATA_DIR"], app.config.get("COLLECTION_FILE"))
    refresh_manager = RefreshManager(store)

    @app.template_filter("money")
    def money_filter(value, currency="USD"):
        if value is None:
            return "N/A"
        symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(str(currency).upper(), "")
        return f"{symbol}{float(value):,.2f}"

    @app.before_request
    def protect_mutations():
        if not app.config.get("ACCESS_PIN") or request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        if request.path in {"/login"}:
            return None
        if not session.get("tracker_unlocked"):
            return jsonify({"error": "Tracker is locked", "login_url": "/login"}), 401
        expected = session.get("csrf_token")
        received = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not expected or not hmac.compare_digest(str(expected), str(received or "")):
            return jsonify({"error": "Security token expired; reload the page"}), 403
        return None

    @app.context_processor
    def shared_template_values():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(24)
        return {
            "csrf_token": session["csrf_token"],
            "access_pin_enabled": bool(app.config.get("ACCESS_PIN")),
            "tracker_unlocked": bool(session.get("tracker_unlocked")),
            "tracker_locked": bool(app.config.get("ACCESS_PIN"))
            and not session.get("tracker_unlocked"),
        }

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not app.config.get("ACCESS_PIN"):
            return redirect(url_for("dashboard"))
        error = ""
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("pin", ""), app.config["ACCESS_PIN"]):
                session.clear()
                session["tracker_unlocked"] = True
                session["csrf_token"] = secrets.token_urlsafe(24)
                return redirect(request.args.get("next") or url_for("dashboard"))
            error = "That PIN did not match."
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", **dashboard_context(store))

    @app.get("/add")
    def add_card_page():
        return render_template("add.html")

    @app.get("/data")
    def data_page():
        state = store.load_state()
        history = store.read_history()
        transactions = store.list_transactions()
        return render_template(
            "data.html",
            health=data_health(state, history, store.read_refresh_status()),
            history=history,
            transactions=transactions,
            transaction_summary=transaction_summary(transactions),
            notifications=store.list_notifications(),
            backups=store.list_backups(),
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "data": store.data_status()})

    @app.get("/api/status")
    def api_status():
        return jsonify(store.data_status())

    @app.get("/download/excel")
    def download_excel():
        _require_download_access(app)
        if not store.excel_path.exists():
            abort(404)
        return send_file(store.excel_path, as_attachment=True)

    @app.get("/download/backup")
    def download_backup():
        _require_download_access(app)
        return send_file(
            store.create_backup(),
            as_attachment=True,
            download_name=f"tcg-tracker-backup-{date.today().isoformat()}.zip",
            mimetype="application/zip",
        )

    @app.get("/api/search/<game>")
    def api_search(game):
        if app.config["DISABLE_NETWORK"]:
            return jsonify([])
        try:
            return jsonify(search_cards(game, request.args.get("q", "")))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        except Exception as exc:
            return jsonify({"error": f"Search failed: {exc}"}), 502

    @app.post("/api/add-card")
    def api_add_card():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(
                store.add_card(
                    payload.get("game"),
                    payload.get("card_line"),
                    payload.get("quantity", 1),
                    payload.get("finish", "regular"),
                    payload.get("buy_price", ""),
                    payload.get("condition", ""),
                )
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/cards/<card_id>")
    def api_card_detail(card_id):
        try:
            return jsonify(store.card_detail(card_id))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.patch("/api/cards/<card_id>")
    def api_update_card(card_id):
        try:
            return jsonify(store.update_card(card_id, request.get_json(silent=True) or {}))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/cards/<card_id>")
    def api_delete_card(card_id):
        try:
            return jsonify(store.delete_card(card_id))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/cards/<card_id>/sell")
    def api_sell_card(card_id):
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(
                store.sell_card(
                    card_id,
                    payload.get("quantity"),
                    payload.get("unit_price"),
                    payload.get("fees", 0),
                    payload.get("shipping", 0),
                    payload.get("notes", ""),
                )
            )
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/cards/<card_id>/archive")
    def api_archive_card(card_id):
        try:
            payload = request.get_json(silent=True) or {}
            return jsonify(store.archive_card(card_id, payload.get("notes", "")))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/wishlist")
    def api_add_wishlist():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(
                store.add_wishlist(
                    payload.get("game"),
                    payload.get("card_line"),
                    payload.get("operator", "<"),
                    payload.get("target_price"),
                    payload.get("alert_enabled", True),
                )
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.patch("/api/wishlist/<wishlist_id>")
    def api_update_wishlist(wishlist_id):
        try:
            return jsonify(store.update_wishlist(wishlist_id, request.get_json(silent=True) or {}))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/wishlist/<wishlist_id>")
    def api_delete_wishlist(wishlist_id):
        try:
            return jsonify(store.delete_wishlist(wishlist_id))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/transactions")
    def api_transactions():
        return jsonify(store.list_transactions())

    @app.post("/api/transactions")
    def api_add_transaction():
        payload = request.get_json(silent=True) or {}
        if payload.get("type") not in {"purchase", "sale", "adjustment"}:
            return jsonify({"error": "Unsupported transaction type"}), 400
        return jsonify(store.add_transaction(payload))

    @app.get("/api/notifications")
    def api_notifications():
        return jsonify(store.list_notifications())

    @app.post("/api/notifications/test")
    def api_test_notification():
        success, message = send_test_alert()
        store.add_notification("system", "Discord test", message)
        return jsonify({"status": "sent" if success else "unavailable", "message": message}), (
            200 if success else 400
        )

    @app.post("/api/refresh")
    def api_refresh():
        if app.config["DISABLE_NETWORK"]:
            return jsonify({"error": "Network refresh is disabled"}), 503
        started, status = refresh_manager.start()
        return jsonify(status), 202 if started else 200

    @app.get("/api/refresh/status")
    def api_refresh_status():
        return jsonify(store.read_refresh_status())

    @app.post("/api/import/preview")
    def api_import_preview():
        upload = request.files.get("file")
        if not upload:
            return jsonify({"error": "Choose a CSV file"}), 400
        try:
            rows = parse_collection_csv(upload.read())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(
            {
                "rows": rows,
                "valid": sum(1 for row in rows if row["valid"]),
                "invalid": sum(1 for row in rows if not row["valid"]),
            }
        )

    @app.post("/api/import/commit")
    def api_import_commit():
        rows = (request.get_json(silent=True) or {}).get("rows", [])
        added = duplicate = invalid = 0
        for row in rows[:5000]:
            if not row.get("valid"):
                invalid += 1
                continue
            try:
                result = store.add_card(
                    row.get("game"),
                    row.get("card_line"),
                    row.get("quantity", 1),
                    row.get("finish", "regular"),
                    row.get("buy_price", ""),
                    row.get("condition", "NM"),
                )
            except (TypeError, ValueError, RuntimeError):
                invalid += 1
            else:
                if result.get("status") == "duplicate":
                    duplicate += 1
                else:
                    added += 1
        return jsonify({"status": "imported", "added": added, "duplicate": duplicate, "invalid": invalid})

    @app.post("/api/backup/restore")
    def api_restore_backup():
        upload = request.files.get("file")
        if not upload:
            return jsonify({"error": "Choose a backup ZIP"}), 400
        try:
            store.save_backup_snapshot("pre-restore")
            result = store.restore_backup(upload.read())
        except (ValueError, OSError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @app.patch("/api/history/<day>")
    def api_update_history(day):
        try:
            return jsonify(store.update_history_point(day, (request.get_json() or {}).get("value")))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/history/<day>")
    def api_delete_history(day):
        try:
            return jsonify(store.delete_history_point(day))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    store.ensure_daily_backup()
    return app


def dashboard_context(store):
    state = store.load_state()
    cards = sorted(state.get("cards", []), key=lambda card: card.get("value") or -1, reverse=True)
    total_value = sum(
        card.get("value") or 0
        for card in cards
        if str(card.get("currency") or "USD").upper() == "USD"
    )
    profit_loss = sum(
        card.get("profit_loss") or 0
        for card in cards
        if card.get("profit_loss") is not None
        and str(card.get("currency") or "USD").upper() == "USD"
    )
    history = store.read_history()
    status = store.data_status()
    wishlist = store.read_wishlist(limit=0)
    transactions = store.list_transactions()
    return {
        "cards": cards,
        "history": history,
        "status": status,
        "total_value": round(total_value, 2),
        "profit_loss": round(profit_loss, 2),
        "card_count": sum(card.get("quantity") or 1 for card in cards),
        "priced_cards": sum(1 for card in cards if card.get("value") is not None),
        "wishlist": wishlist,
        "snapshot": dashboard_snapshot(cards, history, wishlist, status),
        "movers": compute_movers(store.read_card_history(), cards),
        "portfolio": portfolio_breakdowns(cards),
        "transaction_summary": transaction_summary(transactions),
        "notifications": store.list_notifications(limit=5),
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
        wants_above = str(item.get("operator") or "<").startswith(">")
        gap = target - current if wants_above else current - target
        candidates.append((max(gap, 0), gap, wants_above, item))
    if not candidates:
        return None
    _, gap, wants_above, item = min(candidates, key=lambda candidate: candidate[0])
    label = (
        ("above target" if wants_above else "under target")
        if gap <= 0
        else ("below target" if wants_above else "above target")
    )
    return {
        "name": item.get("name") or item.get("card_line") or "Wishlist card",
        "amount": round(abs(gap), 2),
        "label": label,
        "class": "positive" if gap <= 0 else "negative",
    }


def freshness_snapshot(status):
    if status.get("state") == "ok" and not status.get("stale_count"):
        return "Current"
    if status.get("stale_count"):
        return f"{status['stale_count']} stale"
    if status.get("days_old") is not None:
        return f"{status['days_old']} days old"
    return "Needs refresh"


def _require_download_access(app):
    if app.config.get("ACCESS_PIN") and not session.get("tracker_unlocked"):
        abort(401)


def _default_secret(pin):
    seed = f"tcg-tracker:{pin or 'local-only'}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(
        host="0.0.0.0",  # nosec B104 - required for Docker/LAN access
        port=int(os.environ.get("PORT", "8084")),
        debug=debug,
        use_reloader=debug,
    )
