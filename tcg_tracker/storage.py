import io
import json
import os
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from .core import (
    adjusted_price,
    build_card_line,
    card_identity,
    get_refresh_status,
    parse_collection_line,
)

GAME_FILES = {
    "MTG": "mtg_cards.txt",
    "YGO": "ygo_cards.txt",
    "PKM": "pkm_cards.txt",
}
LEGACY_COLLECTION_FILE = "my_cards.txt"
LEGACY_RUN_DATA_FILE = "last_run_data.json"
EXCEL_EXPORT_FILE = "MY_COLLECTION_PRICES.xlsx"
WISHLIST_FILE = "wishlist.txt"
WISHLIST_CACHE_FILE = "wishlist_cache.json"
CARD_HISTORY_FILE = "card_price_history.json"
TRANSACTIONS_FILE = "transactions.json"
NOTIFICATIONS_FILE = "notification_history.json"
WISHLIST_SETTINGS_FILE = "wishlist_settings.json"
REFRESH_STATUS_FILE = "refresh_status.json"

BACKUP_FILES = {
    LEGACY_COLLECTION_FILE,
    *GAME_FILES.values(),
    WISHLIST_FILE,
    "collection_state.json",
    "price_history.csv",
    CARD_HISTORY_FILE,
    LEGACY_RUN_DATA_FILE,
    "last_run_prices.json",
    WISHLIST_CACHE_FILE,
    "wishlist_alerted.json",
    WISHLIST_SETTINGS_FILE,
    TRANSACTIONS_FILE,
    NOTIFICATIONS_FILE,
}


class TrackerStore:
    def __init__(self, data_dir, collection_file=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.collection_file = collection_file or os.environ.get("TCG_TRACKER_COLLECTION_FILE")

    @property
    def state_path(self):
        return self.data_dir / "collection_state.json"

    @property
    def history_path(self):
        return self.data_dir / "price_history.csv"

    @property
    def card_history_path(self):
        return self.data_dir / CARD_HISTORY_FILE

    @property
    def legacy_run_data_path(self):
        return self.data_dir / LEGACY_RUN_DATA_FILE

    @property
    def excel_path(self):
        return self.data_dir / EXCEL_EXPORT_FILE

    @property
    def wishlist_path(self):
        return self.data_dir / WISHLIST_FILE

    @property
    def wishlist_cache_path(self):
        return self.data_dir / WISHLIST_CACHE_FILE

    @property
    def wishlist_settings_path(self):
        return self.data_dir / WISHLIST_SETTINGS_FILE

    @property
    def transactions_path(self):
        return self.data_dir / TRANSACTIONS_FILE

    @property
    def notifications_path(self):
        return self.data_dir / NOTIFICATIONS_FILE

    @property
    def refresh_status_path(self):
        return self.data_dir / REFRESH_STATUS_FILE

    @property
    def refresh_lock_path(self):
        return self.data_dir / ".refresh.lock"

    @property
    def backups_path(self):
        return self.data_dir / "backups"

    @property
    def unified_collection_path(self):
        if self.collection_file:
            return self.data_dir / self.collection_file
        legacy_path = self.data_dir / LEGACY_COLLECTION_FILE
        return legacy_path if legacy_path.exists() else None

    def card_file(self, game):
        return self.data_dir / GAME_FILES[self.normalize_game(game)]

    def read_entries(self, game=None):
        game_filter = self.normalize_game(game) if game else None
        return [
            row["entry"]
            for row in self._collection_rows()
            if not game_filter or row["game"] == game_filter
        ]

    def add_card(self, game, card_line, quantity=1, finish="regular", buy_price="", condition=""):
        normalized_game = self.normalize_game(game)
        path = self.unified_collection_path or self.card_file(normalized_game)
        new_line = build_card_line(card_line, quantity, finish, buy_price, condition)
        file_line = new_line
        if path.name == LEGACY_COLLECTION_FILE and normalized_game != "MTG":
            file_line = f"[{normalized_game}] {new_line}"

        with self.data_lock():
            existing = self._read_file_lines(path)
            active = {line.strip().lower() for line in existing if line.strip()}
            if file_line.lower() in active:
                return {
                    "status": "duplicate",
                    "line": file_line,
                    "card_id": card_identity(normalized_game, new_line),
                }
            existing.append(file_line)
            self._write_lines(path, existing)

        card_id = card_identity(normalized_game, new_line)
        self.save_state(self.load_state())
        buy_value = _float_or_none(buy_price)
        if buy_value is not None:
            self.add_transaction(
                {
                    "type": "purchase",
                    "card_id": card_id,
                    "game": normalized_game,
                    "name": str(card_line).strip(),
                    "quantity": int(quantity or 1),
                    "unit_price": buy_value,
                    "total_amount": round(buy_value * int(quantity or 1), 2),
                    "notes": "Added to collection",
                }
            )
        return {"status": "added", "line": file_line, "card_id": card_id}

    def update_card(self, card_id, payload):
        row = self._find_collection_row(card_id)
        entry = row["entry"]
        card_line = str(payload.get("card_line") or entry.name).strip()
        quantity = int(payload.get("quantity", entry.quantity) or 1)
        if quantity < 1:
            raise ValueError("Quantity must be at least 1")
        finish = str(payload.get("finish", entry.finish) or "regular").lower()
        condition = str(payload.get("condition", entry.condition) or "NM").upper()
        buy_price = payload.get("buy_price", entry.buy_price if entry.buy_price is not None else "")
        replacement = build_card_line(card_line, quantity, finish, buy_price, condition)
        file_line = replacement
        if row["path"].name == LEGACY_COLLECTION_FILE and row["game"] != "MTG":
            file_line = f"[{row['game']}] {replacement}"

        with self.data_lock():
            lines = self._read_file_lines(row["path"])
            lines[row["index"]] = file_line
            self._write_lines(row["path"], lines)

        new_id = card_identity(row["game"], replacement)
        state = self._read_json(self.state_path, {})
        for card in state.get("cards", []):
            if card.get("card_id") == card_id or card.get("source_line") == entry.raw_line:
                source_changed = entry.name != card_line or entry.finish != finish
                card.update(
                    {
                        "card_id": new_id,
                        "card_key": f"{row['game']}|{replacement}",
                        "source_line": replacement,
                        "quantity": quantity,
                        "finish": finish,
                        "condition": condition,
                        "buy_price": _float_or_none(buy_price),
                    }
                )
                if source_changed:
                    card.update({"price": None, "value": None, "profit_loss": None, "stale": True})
                else:
                    _revalue_card(card)
                break
        self.save_state(state if state else self.load_state())
        return {"status": "updated", "card_id": new_id, "line": file_line}

    def delete_card(self, card_id):
        row = self._find_collection_row(card_id)
        with self.data_lock():
            lines = self._read_file_lines(row["path"])
            del lines[row["index"]]
            self._write_lines(row["path"], lines)
        state = self._read_json(self.state_path, {})
        state["cards"] = [
            card
            for card in state.get("cards", [])
            if card.get("card_id") != card_id and card.get("source_line") != row["entry"].raw_line
        ]
        state["total_value"] = round(sum(card.get("value") or 0 for card in state["cards"]), 2)
        self.save_state(state)
        return {"status": "removed", "card_id": card_id}

    def sell_card(self, card_id, quantity, unit_price, fees=0, shipping=0, notes=""):
        row = self._find_collection_row(card_id)
        entry = row["entry"]
        quantity = int(quantity or 0)
        if quantity < 1 or quantity > entry.quantity:
            raise ValueError(f"Quantity must be between 1 and {entry.quantity}")
        unit_price = float(unit_price)
        fees = float(fees or 0)
        shipping = float(shipping or 0)
        gross = round(unit_price * quantity, 2)
        net = round(gross - fees - shipping, 2)
        cost_basis = round((entry.buy_price or 0) * quantity, 2) if entry.buy_price is not None else None
        transaction = self.add_transaction(
            {
                "type": "sale",
                "card_id": card_id,
                "game": entry.game,
                "name": entry.name,
                "quantity": quantity,
                "unit_price": unit_price,
                "gross_amount": gross,
                "fees": fees,
                "shipping": shipping,
                "net_amount": net,
                "cost_basis": cost_basis,
                "realized_profit": round(net - cost_basis, 2) if cost_basis is not None else None,
                "notes": str(notes or "").strip(),
            }
        )
        if quantity == entry.quantity:
            self.delete_card(card_id)
        else:
            self.update_card(card_id, {"quantity": entry.quantity - quantity})
        return transaction

    def archive_card(self, card_id, notes=""):
        row = self._find_collection_row(card_id)
        entry = row["entry"]
        transaction = self.add_transaction(
            {
                "type": "archive",
                "card_id": card_id,
                "game": entry.game,
                "name": entry.name,
                "quantity": entry.quantity,
                "notes": str(notes or "").strip(),
            }
        )
        self.delete_card(card_id)
        return transaction

    def card_detail(self, card_id):
        state = self.load_state()
        card = next((item for item in state.get("cards", []) if item.get("card_id") == card_id), None)
        if not card:
            raise KeyError("Card not found")
        detail = dict(card)
        row = self._find_collection_row(card_id)
        detail["editable_name"] = row["entry"].name
        detail["history"] = self.card_history_for(card)
        return detail

    def load_state(self):
        if self.state_path.exists():
            state = self._read_json(self.state_path, {})
        else:
            state = self._load_legacy_state() or {"last_updated": None, "cards": [], "failures": []}
        entries = self.read_entries()
        state["cards"] = self._reconcile_cards(state.get("cards", []), entries)
        state.setdefault("failures", [])
        state["total_value"] = round(sum(card.get("value") or 0 for card in state["cards"]), 2)
        return state

    def save_state(self, state):
        self._write_json(self.state_path, state)

    def read_history(self):
        if not self.history_path.exists():
            return []
        rows = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                rows.append({"date": parts[0], "value": float(parts[1])})
            except ValueError:
                continue
        return rows

    def update_history_point(self, day, value):
        datetime.strptime(day, "%Y-%m-%d")
        rows = self.read_history()
        found = False
        for row in rows:
            if row["date"] == day:
                row["value"] = round(float(value), 2)
                found = True
        if not found:
            rows.append({"date": day, "value": round(float(value), 2)})
        rows.sort(key=lambda row: row["date"])
        self._write_history(rows)
        return {"status": "updated", "date": day}

    def delete_history_point(self, day):
        rows = self.read_history()
        filtered = [row for row in rows if row["date"] != day]
        if len(filtered) == len(rows):
            raise KeyError("History point not found")
        self._write_history(filtered)
        return {"status": "removed", "date": day}

    def read_card_history(self):
        return self._read_json(self.card_history_path, {})

    def save_card_history(self, cards, today=None, retention_days=365):
        history = self.read_card_history()
        prices = {}
        for card in cards:
            if card.get("stale") or card.get("unit_value") is None:
                continue
            prices[card.get("card_id") or card.get("card_key")] = card["unit_value"]
        if prices:
            history[(today or date.today()).isoformat()] = prices
        for old_day in sorted(history)[:-retention_days]:
            del history[old_day]
        self._write_json(self.card_history_path, history)

    def card_history_for(self, card):
        aliases = {
            card.get("card_id"),
            card.get("card_key"),
            f"{card.get('game', '')}|{card.get('source_line', '')}",
        }
        rows = []
        for day, values in sorted(self.read_card_history().items()):
            for alias in aliases:
                if alias and alias in values:
                    rows.append({"date": day, "value": _float_or_none(values[alias])})
                    break
        return rows

    def read_wishlist(self, limit=8):
        if not self.wishlist_path.exists():
            return []
        cache = self._wishlist_cache_by_key()
        settings = self._read_json(self.wishlist_settings_path, {})
        items = []
        for raw_line in self._read_file_lines(self.wishlist_path):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            game, body = self._split_game_prefix(stripped)
            name, target = self._split_wishlist_target(body)
            operator, target_price = self._parse_wishlist_target(target)
            wishlist_id = self._wishlist_id(game, name)
            cached = cache.get(self._wishlist_key(game, name), {})
            current_price = cached.get("current_price")
            is_deal = bool(cached.get("is_deal"))
            items.append(
                {
                    "wishlist_id": wishlist_id,
                    "game": game,
                    "name": cached.get("name") or name,
                    "card_line": name,
                    "target": cached.get("target_label") or target,
                    "target_price": cached.get("target_price", target_price),
                    "operator": cached.get("operator") or operator,
                    "current_price": current_price,
                    "set": cached.get("set", ""),
                    "image": cached.get("image", ""),
                    "uri": cached.get("uri", "#"),
                    "source": cached.get("source", ""),
                    "currency": cached.get("currency", "USD"),
                    "is_deal": is_deal,
                    "last_updated": cached.get("last_updated"),
                    "alert_enabled": settings.get(wishlist_id, {}).get("alert_enabled", True),
                    "progress": _target_progress(current_price, target_price, operator, is_deal),
                    "raw_line": stripped,
                }
            )
            if limit and len(items) >= limit:
                break
        return items

    def add_wishlist(self, game, card_line, operator, target_price, alert_enabled=True):
        game = self.normalize_game(game)
        card_line = " ".join(str(card_line or "").split())
        if not card_line:
            raise ValueError("Card name is required")
        operator = operator if operator in {"<", "<=", ">", ">="} else "<"
        target_price = float(target_price)
        wishlist_id = self._wishlist_id(game, card_line)
        if any(item["wishlist_id"] == wishlist_id for item in self.read_wishlist(limit=0)):
            return {"status": "duplicate", "wishlist_id": wishlist_id}
        prefix = "" if game == "MTG" else f"[{game}] "
        line = f"{prefix}{card_line} | {operator} {target_price:.2f}"
        with self.data_lock():
            lines = self._read_file_lines(self.wishlist_path)
            lines.append(line)
            self._write_lines(self.wishlist_path, lines)
        self._set_wishlist_setting(wishlist_id, alert_enabled)
        return {"status": "added", "wishlist_id": wishlist_id, "line": line}

    def update_wishlist(self, wishlist_id, payload):
        row = self._find_wishlist_row(wishlist_id)
        game = self.normalize_game(payload.get("game", row["game"]))
        card_line = " ".join(str(payload.get("card_line") or row["card_line"]).split())
        operator = payload.get("operator", row["operator"])
        if operator not in {"<", "<=", ">", ">="}:
            raise ValueError("Unsupported target operator")
        target_price = float(payload.get("target_price", row["target_price"]))
        prefix = "" if game == "MTG" else f"[{game}] "
        replacement = f"{prefix}{card_line} | {operator} {target_price:.2f}"
        with self.data_lock():
            lines = self._read_file_lines(self.wishlist_path)
            lines[row["index"]] = replacement
            self._write_lines(self.wishlist_path, lines)
        new_id = self._wishlist_id(game, card_line)
        settings = self._read_json(self.wishlist_settings_path, {})
        old = settings.pop(wishlist_id, {})
        old["alert_enabled"] = bool(payload.get("alert_enabled", old.get("alert_enabled", True)))
        settings[new_id] = old
        self._write_json(self.wishlist_settings_path, settings)
        return {"status": "updated", "wishlist_id": new_id, "line": replacement}

    def delete_wishlist(self, wishlist_id):
        row = self._find_wishlist_row(wishlist_id)
        with self.data_lock():
            lines = self._read_file_lines(self.wishlist_path)
            del lines[row["index"]]
            self._write_lines(self.wishlist_path, lines)
        settings = self._read_json(self.wishlist_settings_path, {})
        settings.pop(wishlist_id, None)
        self._write_json(self.wishlist_settings_path, settings)
        return {"status": "removed", "wishlist_id": wishlist_id}

    def save_wishlist_cache(self, items, today=None):
        payload = {"last_updated": (today or date.today()).isoformat(), "items": items}
        self._write_json(self.wishlist_cache_path, payload)

    def record_deal_notifications(self, previous_items, current_items):
        previous = {item.get("wishlist_id"): bool(item.get("is_deal")) for item in previous_items}
        created = []
        for item in current_items:
            if not item.get("is_deal") or previous.get(item.get("wishlist_id")):
                continue
            if not item.get("alert_enabled", True):
                continue
            created.append(
                self.add_notification(
                    "wishlist",
                    f"{item.get('name')} reached its target",
                    f"Current price {item.get('current_price')} · target {item.get('target')}",
                    item.get("wishlist_id"),
                )
            )
        return created

    def list_transactions(self, limit=100):
        rows = self._read_json(self.transactions_path, [])
        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows[:limit] if limit else rows

    def add_transaction(self, payload):
        transaction = dict(payload)
        transaction.setdefault("transaction_id", uuid.uuid4().hex[:16])
        transaction.setdefault("created_at", _utc_now())
        rows = self._read_json(self.transactions_path, [])
        rows.append(transaction)
        self._write_json(self.transactions_path, rows[-1000:])
        return transaction

    def list_notifications(self, limit=100):
        rows = self._read_json(self.notifications_path, [])
        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows[:limit]

    def add_notification(self, category, title, message, entity_id=""):
        item = {
            "notification_id": uuid.uuid4().hex[:16],
            "category": category,
            "title": title,
            "message": message,
            "entity_id": entity_id,
            "created_at": _utc_now(),
        }
        rows = self._read_json(self.notifications_path, [])
        rows.append(item)
        self._write_json(self.notifications_path, rows[-300:])
        return item

    def data_status(self, today=None):
        state = self.load_state()
        refresh = get_refresh_status(
            state.get("last_updated"), today=today or date.today(), stale_after_days=2
        )
        return {
            "state": refresh["state"],
            "days_old": refresh["days_old"],
            "last_updated": state.get("last_updated"),
            "card_count": len(state.get("cards", [])),
            "failure_count": len(state.get("failures", [])),
            "stale_count": sum(1 for card in state.get("cards", []) if card.get("stale")),
            "has_excel_export": self.excel_path.exists(),
            "wishlist_count": self.count_wishlist_items(),
            "refresh": self.read_refresh_status(),
        }

    def count_wishlist_items(self):
        return len(self.read_wishlist(limit=0))

    def read_refresh_status(self):
        return self._read_json(
            self.refresh_status_path,
            {"state": "idle", "current": 0, "total": 0, "message": "Ready"},
        )

    def save_refresh_status(self, status):
        self._write_json(self.refresh_status_path, status)

    def create_backup(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = {"created_at": _utc_now(), "version": 2, "files": []}
            for name in sorted(BACKUP_FILES):
                path = self.data_dir / name
                if path.exists() and path.is_file():
                    archive.write(path, arcname=name)
                    manifest["files"].append(name)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        buffer.seek(0)
        return buffer

    def save_backup_snapshot(self, label="automatic", keep=14):
        if not any((self.data_dir / name).exists() for name in BACKUP_FILES):
            return None
        self.backups_path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.backups_path / f"tcg-tracker-{label}-{stamp}.zip"
        self._atomic_write_bytes(path, self.create_backup().getvalue())
        backups = sorted(self.backups_path.glob("tcg-tracker-*.zip"), reverse=True)
        for old_path in backups[keep:]:
            old_path.unlink(missing_ok=True)
        return path

    def ensure_daily_backup(self):
        if not any((self.data_dir / name).exists() for name in BACKUP_FILES):
            return None
        self.backups_path.mkdir(parents=True, exist_ok=True)
        today_key = date.today().strftime("%Y%m%d")
        existing = list(self.backups_path.glob(f"tcg-tracker-daily-{today_key}-*.zip"))
        return existing[0] if existing else self.save_backup_snapshot("daily")

    def list_backups(self, limit=14):
        if not self.backups_path.exists():
            return []
        rows = []
        for path in sorted(self.backups_path.glob("tcg-tracker-*.zip"), reverse=True)[:limit]:
            rows.append(
                {
                    "name": path.name,
                    "size_kb": round(path.stat().st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes"),
                }
            )
        return rows

    def restore_backup(self, raw_bytes):
        if len(raw_bytes) > 25 * 1024 * 1024:
            raise ValueError("Backup files must be 25 MB or smaller")
        restored = []
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            for info in archive.infolist():
                name = Path(info.filename).name
                if info.is_dir() or name == "manifest.json":
                    continue
                if info.filename != name or name not in BACKUP_FILES:
                    raise ValueError(f"Backup contains an unsupported file: {info.filename}")
                if info.file_size > 10 * 1024 * 1024:
                    raise ValueError(f"Backup file is too large: {name}")
                self._atomic_write_bytes(self.data_dir / name, archive.read(info))
                restored.append(name)
        if not restored:
            raise ValueError("No tracker data was found in the backup")
        return {"status": "restored", "files": restored}

    @contextmanager
    def data_lock(self, timeout=5):
        lock_path = self.data_dir / ".data.lock"
        started = time.monotonic()
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() - started >= timeout:
                    raise RuntimeError("Tracker data is busy; try again") from None
                try:
                    if time.time() - lock_path.stat().st_mtime > 60:
                        lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
                time.sleep(0.05)
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            yield
        finally:
            os.close(descriptor)
            lock_path.unlink(missing_ok=True)

    def _collection_rows(self):
        unified = self.unified_collection_path
        rows = []
        if unified:
            for index, raw in enumerate(self._read_file_lines(unified)):
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                game, body = self._split_game_prefix(stripped)
                rows.append(
                    {
                        "path": unified,
                        "index": index,
                        "game": game,
                        "file_line": raw,
                        "entry": parse_collection_line(body, game),
                    }
                )
            return rows
        for game in GAME_FILES:
            path = self.card_file(game)
            for index, raw in enumerate(self._read_file_lines(path)):
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                rows.append(
                    {
                        "path": path,
                        "index": index,
                        "game": game,
                        "file_line": raw,
                        "entry": parse_collection_line(stripped, game),
                    }
                )
        return rows

    def _find_collection_row(self, card_id):
        for row in self._collection_rows():
            if card_identity(row["game"], row["entry"].raw_line) == card_id:
                return row
        raise KeyError("Card not found")

    def _find_wishlist_row(self, wishlist_id):
        for index, raw in enumerate(self._read_file_lines(self.wishlist_path)):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            game, body = self._split_game_prefix(stripped)
            card_line, target = self._split_wishlist_target(body)
            operator, target_price = self._parse_wishlist_target(target)
            if self._wishlist_id(game, card_line) == wishlist_id:
                return {
                    "index": index,
                    "game": game,
                    "card_line": card_line,
                    "operator": operator,
                    "target_price": target_price,
                }
        raise KeyError("Wishlist target not found")

    def _reconcile_cards(self, previous_cards, entries):
        by_id = {card.get("card_id"): card for card in previous_cards if card.get("card_id")}
        by_source = {
            (card.get("game"), card.get("source_line")): card
            for card in previous_cards
            if card.get("source_line")
        }
        cards = []
        for index, entry in enumerate(entries):
            identity = card_identity(entry.game, entry.raw_line)
            card = by_id.get(identity) or by_source.get((entry.game, entry.raw_line))
            if not card and index < len(previous_cards):
                candidate = previous_cards[index]
                if candidate.get("game") == entry.game:
                    card = candidate
            if card:
                card = dict(card)
                card.update(
                    {
                        "card_id": identity,
                        "card_key": f"{entry.game}|{entry.raw_line}",
                        "source_line": entry.raw_line,
                        "quantity": entry.quantity,
                        "finish": entry.finish,
                        "condition": entry.condition,
                        "buy_price": entry.buy_price,
                    }
                )
                _revalue_card(card)
            else:
                card = entry_to_card(entry)
            cards.append(card)
        return cards

    def _load_legacy_state(self):
        if not self.legacy_run_data_path.exists():
            return None
        run_data = self._read_json(self.legacy_run_data_path, {})
        cards = []
        seen_keys = set()
        for entry in self.read_entries():
            card_key = f"{entry.game}|{entry.raw_line}"
            seen_keys.add(card_key)
            cached = run_data.get(card_key)
            cards.append(cached_item_to_card(cached, entry, card_key) if cached else entry_to_card(entry))
        for card_key, cached in run_data.items():
            if card_key not in seen_keys:
                cards.append(cached_item_to_card(cached, None, card_key))
        return {
            "last_updated": self._last_refresh_date(),
            "total_value": round(sum(card.get("value") or 0 for card in cards), 2),
            "cards": cards,
            "failures": [],
            "source": LEGACY_RUN_DATA_FILE,
        }

    def _last_refresh_date(self):
        rows = self.read_history()
        if rows:
            return rows[-1]["date"]
        try:
            return date.fromtimestamp(self.legacy_run_data_path.stat().st_mtime).isoformat()
        except OSError:
            return None

    def _wishlist_cache_by_key(self):
        cache = self._read_json(self.wishlist_cache_path, {})
        last_updated = cache.get("last_updated") if isinstance(cache, dict) else None
        by_key = {}
        for item in cache.get("items", []) if isinstance(cache, dict) else []:
            game = item.get("game", "MTG")
            card_line = item.get("card_line") or item.get("name", "")
            normalized = dict(item)
            normalized["last_updated"] = item.get("last_updated") or last_updated
            by_key[self._wishlist_key(game, card_line)] = normalized
        return by_key

    def _set_wishlist_setting(self, wishlist_id, alert_enabled):
        settings = self._read_json(self.wishlist_settings_path, {})
        settings.setdefault(wishlist_id, {})["alert_enabled"] = bool(alert_enabled)
        self._write_json(self.wishlist_settings_path, settings)

    def _write_history(self, rows):
        text = "".join(f"{row['date']},{float(row['value']):.2f}\n" for row in rows)
        self._atomic_write_text(self.history_path, text)

    def _write_lines(self, path, lines):
        text = "\n".join(lines)
        if lines:
            text += "\n"
        self._atomic_write_text(path, text)

    def _write_json(self, path, value):
        self._atomic_write_text(path, json.dumps(value, indent=2))

    def _atomic_write_text(self, path, text):
        self._atomic_write_bytes(path, text.encode("utf-8"))

    @staticmethod
    def _atomic_write_bytes(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_bytes(content)
        os.replace(temp_path, path)

    @staticmethod
    def _read_json(path, fallback):
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    @staticmethod
    def _read_file_lines(path):
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    @staticmethod
    def _split_game_prefix(line):
        stripped = str(line or "").strip()
        upper = stripped.upper()
        for game in GAME_FILES:
            prefix = f"[{game}]"
            if upper.startswith(prefix):
                return game, stripped[len(prefix) :].strip()
        return "MTG", stripped

    @staticmethod
    def _split_wishlist_target(line):
        if "|" not in line:
            return line.strip(), ""
        name, target = line.split("|", 1)
        return name.strip(), target.strip()

    @staticmethod
    def _parse_wishlist_target(target):
        target_text = str(target or "").strip().replace("$", "")
        operator = "<"
        for candidate in ("<=", ">=", "<", ">"):
            if target_text.startswith(candidate):
                operator = candidate
                target_text = target_text[len(candidate) :].strip()
                break
        return operator, _float_or_none(target_text)

    @staticmethod
    def _wishlist_key(game, card_line):
        return f"wishlist|{str(game).upper()}|{' '.join(str(card_line or '').split()).lower()}"

    @staticmethod
    def _wishlist_id(game, card_line):
        return card_identity(f"wishlist-{game}", card_line)

    @staticmethod
    def normalize_game(game):
        normalized = str(game or "").upper()
        if normalized not in GAME_FILES:
            raise ValueError(f"Unsupported game: {game}")
        return normalized


def entry_to_card(entry):
    identity = card_identity(entry.game, entry.raw_line)
    return {
        "card_id": identity,
        "card_key": f"{entry.game}|{entry.raw_line}",
        "source_line": entry.raw_line,
        "game": entry.game,
        "name": entry.name,
        "set": "",
        "price": None,
        "unit_value": None,
        "quantity": entry.quantity,
        "finish": entry.finish,
        "condition": entry.condition,
        "condition_multiplier": 1.0,
        "buy_price": entry.buy_price,
        "value": None,
        "profit_loss": None,
        "currency": "USD",
        "source": "",
        "price_as_of": None,
        "image": "",
        "uri": "#",
        "stale": True,
    }


def cached_item_to_card(cached, entry=None, card_key=""):
    cached = cached or {}
    data = cached.get("data") or {}
    quantity = cached.get("quantity") or (entry.quantity if entry else 1)
    value = _float_or_none(cached.get("sort_val"))
    if value is None:
        value = _float_or_none(cached.get("price_str"))
    game = data.get("game") or (entry.game if entry else _game_from_key(card_key))
    source_line = entry.raw_line if entry else _name_from_key(card_key)
    unit_value = round(value / quantity, 2) if value is not None and quantity else None
    return {
        "card_id": card_identity(game, source_line),
        "card_key": cached.get("card_key") or card_key,
        "source_line": source_line,
        "game": game,
        "name": data.get("name") or (entry.name if entry else _name_from_key(card_key)),
        "set": data.get("set", ""),
        "price": data.get("price"),
        "unit_value": unit_value,
        "quantity": quantity,
        "finish": "foil" if cached.get("is_foil") else (entry.finish if entry else "regular"),
        "condition": entry.condition if entry else "NM",
        "condition_multiplier": 1.0,
        "buy_price": entry.buy_price if entry else None,
        "value": value,
        "profit_loss": _float_or_none(cached.get("profit_loss")),
        "currency": data.get("currency", "USD"),
        "source": data.get("source", "Legacy cache"),
        "price_as_of": None,
        "image": data.get("image", ""),
        "uri": data.get("uri", "#"),
        "stale": bool(cached.get("stale", False)),
    }


def _revalue_card(card):
    base_price = _float_or_none(card.get("price"))
    unit_value = adjusted_price(base_price, card.get("condition"))
    card["unit_value"] = unit_value
    card["condition_multiplier"] = (
        round(unit_value / base_price, 2) if unit_value is not None and base_price else 1.0
    )
    quantity = int(card.get("quantity") or 1)
    card["value"] = round(unit_value * quantity, 2) if unit_value is not None else None
    buy_price = _float_or_none(card.get("buy_price"))
    card["profit_loss"] = (
        round((unit_value - buy_price) * quantity, 2)
        if unit_value is not None and buy_price is not None
        else None
    )


def _target_progress(current, target, operator, is_deal):
    current = _float_or_none(current)
    target = _float_or_none(target)
    if current is None or target in (None, 0):
        return None
    if is_deal:
        return 100.0
    gap = target - current if str(operator).startswith(">") else current - target
    return round(max(0, min(100, 100 - (max(gap, 0) / abs(target) * 100))), 1)


def _float_or_none(value):
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _game_from_key(card_key):
    game = str(card_key).split("|", 1)[0]
    return game if game in GAME_FILES else "MTG"


def _name_from_key(card_key):
    return str(card_key).split("|", 1)[1] if "|" in str(card_key) else str(card_key or "")


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
