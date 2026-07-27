import json
import os
from datetime import date
from pathlib import Path

from .core import build_card_line, get_refresh_status, parse_collection_line

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
    def unified_collection_path(self):
        if self.collection_file:
            return self.data_dir / self.collection_file

        legacy_path = self.data_dir / LEGACY_COLLECTION_FILE
        if legacy_path.exists():
            return legacy_path
        return None

    def card_file(self, game):
        game = self.normalize_game(game)
        return self.data_dir / GAME_FILES[game]

    def read_entries(self, game=None):
        unified_path = self.unified_collection_path
        if unified_path:
            return self._read_unified_entries(unified_path, game)

        games = [self.normalize_game(game)] if game else GAME_FILES.keys()
        entries = []
        for current_game in games:
            path = self.card_file(current_game)
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped:
                    entries.append(parse_collection_line(stripped, current_game))
        return entries

    def add_card(self, game, card_line, quantity=1, finish="regular", buy_price="", condition=""):
        normalized_game = self.normalize_game(game)
        path = self.unified_collection_path or self.card_file(normalized_game)
        new_line = build_card_line(card_line, quantity, finish, buy_price, condition)
        if path.name == LEGACY_COLLECTION_FILE and normalized_game != "MTG":
            new_line = f"[{normalized_game}] {new_line}"
        existing = self._read_lines(path)

        if new_line.lower() in {line.lower() for line in existing}:
            return {"status": "duplicate", "line": new_line}

        existing.append(new_line)
        path.write_text("\n".join(existing) + "\n", encoding="utf-8")
        return {"status": "added", "line": new_line}

    def load_state(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))

        legacy_state = self._load_legacy_state()
        if legacy_state:
            return legacy_state

        entries = self.read_entries()
        return {
            "last_updated": None,
            "cards": [entry_to_card(entry) for entry in entries],
            "failures": [],
        }

    def save_state(self, state):
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

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

    def read_wishlist(self, limit=8):
        if not self.wishlist_path.exists():
            return []

        cache = self._wishlist_cache_by_key()
        items = []
        for line in self.wishlist_path.read_text(encoding="utf-8").splitlines():
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue
            game, body = self._split_game_prefix(raw_line)
            name, target = self._split_wishlist_target(body)
            operator, target_price = self._parse_wishlist_target(target)
            cached = cache.get(self._wishlist_key(game, name), {})
            items.append(
                {
                    "game": game,
                    "name": cached.get("name") or name,
                    "card_line": name,
                    "target": cached.get("target_label") or target,
                    "target_price": cached.get("target_price", target_price),
                    "operator": cached.get("operator") or operator,
                    "current_price": cached.get("current_price"),
                    "set": cached.get("set", ""),
                    "image": cached.get("image", ""),
                    "uri": cached.get("uri", "#"),
                    "is_deal": bool(cached.get("is_deal")),
                    "last_updated": cached.get("last_updated"),
                    "raw_line": raw_line,
                }
            )
            if limit and len(items) >= limit:
                break
        return items

    def save_wishlist_cache(self, items, today=None):
        payload = {
            "last_updated": (today or date.today()).isoformat(),
            "items": items,
        }
        self.wishlist_cache_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def data_status(self, today=None):
        state = self.load_state()
        refresh = get_refresh_status(
            state.get("last_updated"),
            today=today or date.today(),
            stale_after_days=2,
        )
        return {
            "state": refresh["state"],
            "days_old": refresh["days_old"],
            "last_updated": state.get("last_updated"),
            "card_count": len(state.get("cards", [])),
            "failure_count": len(state.get("failures", [])),
            "has_excel_export": self.excel_path.exists(),
            "wishlist_count": self.count_wishlist_items(),
        }

    def count_wishlist_items(self):
        if not self.wishlist_path.exists():
            return 0
        return sum(
            1
            for line in self.wishlist_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    def _read_unified_entries(self, path, game=None):
        game_filter = self.normalize_game(game) if game else None
        entries = []
        if not path.exists():
            return entries

        for line in path.read_text(encoding="utf-8").splitlines():
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue
            current_game, card_line = self._split_game_prefix(raw_line)
            if game_filter and current_game != game_filter:
                continue
            entries.append(parse_collection_line(card_line, current_game))
        return entries

    def _load_legacy_state(self):
        if not self.legacy_run_data_path.exists():
            return None

        try:
            run_data = json.loads(self.legacy_run_data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

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
        try:
            return operator, float(target_text)
        except ValueError:
            return operator, None

    def _wishlist_cache_by_key(self):
        if not self.wishlist_cache_path.exists():
            return {}

        try:
            cache = json.loads(self.wishlist_cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        last_updated = cache.get("last_updated")
        items = cache.get("items") if isinstance(cache, dict) else []
        by_key = {}
        for item in items or []:
            game = item.get("game", "MTG")
            card_line = item.get("card_line") or item.get("name", "")
            normalized = dict(item)
            normalized["last_updated"] = item.get("last_updated") or last_updated
            by_key[self._wishlist_key(game, card_line)] = normalized
        return by_key

    @staticmethod
    def _wishlist_key(game, card_line):
        return f"wishlist|{str(game).upper()}|{' '.join(str(card_line or '').split()).lower()}"

    @staticmethod
    def normalize_game(game):
        normalized = str(game or "").upper()
        if normalized not in GAME_FILES:
            raise ValueError(f"Unsupported game: {game}")
        return normalized

    @staticmethod
    def _read_lines(path):
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def entry_to_card(entry):
    return {
        "game": entry.game,
        "name": entry.name,
        "set": "",
        "price": None,
        "quantity": entry.quantity,
        "finish": entry.finish,
        "condition": entry.condition,
        "buy_price": entry.buy_price,
        "value": None,
        "profit_loss": None,
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

    return {
        "game": data.get("game") or (entry.game if entry else _game_from_key(card_key)),
        "name": data.get("name") or (entry.name if entry else _name_from_key(card_key)),
        "set": data.get("set", ""),
        "price": data.get("price"),
        "quantity": quantity,
        "finish": "foil" if cached.get("is_foil") else (entry.finish if entry else "regular"),
        "condition": entry.condition if entry else "NM",
        "buy_price": entry.buy_price if entry else None,
        "value": value,
        "profit_loss": _float_or_none(cached.get("profit_loss")),
        "image": data.get("image", ""),
        "uri": data.get("uri", "#"),
        "stale": bool(cached.get("stale", False)),
        "card_key": cached.get("card_key") or card_key,
    }


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
    if "|" not in str(card_key):
        return str(card_key or "")
    return str(card_key).split("|", 1)[1]
