import csv
import io

ALIASES = {
    "game": ("game", "product line", "category", "tcg"),
    "name": ("card line", "card name", "product name", "name", "card"),
    "number": ("collector number", "card number", "number", "collector #"),
    "quantity": ("quantity", "qty", "amount", "count"),
    "finish": ("finish", "printing", "foil"),
    "condition": ("condition", "card condition"),
    "buy_price": ("buy price", "purchase price", "price paid", "cost", "cost basis"),
}


def parse_collection_csv(raw_bytes):
    if len(raw_bytes) > 5 * 1024 * 1024:
        raise ValueError("CSV files must be 5 MB or smaller")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("cp1252")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The CSV does not have a header row")
    headers = {header.strip().lower(): header for header in reader.fieldnames if header}
    rows = []
    for row_number, source in enumerate(reader, start=2):
        name = _value(source, headers, "name")
        number = _value(source, headers, "number")
        if number and "#" not in name:
            name = f"{name} # {number}"
        game = _normalize_game(_value(source, headers, "game"))
        quantity = _positive_int(_value(source, headers, "quantity"), 1)
        finish = _normalize_finish(_value(source, headers, "finish"))
        condition = (_value(source, headers, "condition") or "NM").upper()
        buy_price = _number_or_blank(_value(source, headers, "buy_price"))
        errors = []
        if not name:
            errors.append("Missing card name")
        if game not in {"MTG", "YGO", "PKM"}:
            errors.append("Unknown game")
        rows.append(
            {
                "row": row_number,
                "game": game,
                "card_line": name,
                "quantity": quantity,
                "finish": finish,
                "condition": condition,
                "buy_price": buy_price,
                "valid": not errors,
                "errors": errors,
            }
        )
    return rows


def _value(row, headers, key):
    for alias in ALIASES[key]:
        original = headers.get(alias)
        if original:
            return str(row.get(original) or "").strip()
    return ""


def _normalize_game(value):
    normalized = str(value or "MTG").strip().upper()
    if normalized in {"MAGIC", "MAGIC: THE GATHERING", "MAGIC THE GATHERING"}:
        return "MTG"
    if normalized in {"YU-GI-OH", "YU-GI-OH!", "YUGIOH"}:
        return "YGO"
    if normalized in {"POKEMON", "POKEMON TCG"}:
        return "PKM"
    return normalized


def _normalize_finish(value):
    normalized = str(value or "regular").strip().lower()
    if "etched" in normalized:
        return "etched"
    if normalized in {"true", "yes", "1"} or "foil" in normalized or "holo" in normalized:
        return "foil"
    return "regular"


def _positive_int(value, default):
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _number_or_blank(value):
    if value in (None, ""):
        return ""
    try:
        return f"{float(str(value).replace('$', '').replace(',', '')):.2f}"
    except ValueError:
        return ""
