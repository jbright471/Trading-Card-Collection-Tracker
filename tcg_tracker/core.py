import csv
import hashlib
import html
import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

FINISH_LABELS = {
    "regular": "",
    "foil": "Foil",
    "etched": "Etched",
}

CONDITION_MULTIPLIERS = {
    "M": 1.05,
    "NM": 1.0,
    "LP": 0.85,
    "MP": 0.70,
    "HP": 0.50,
    "DMG": 0.30,
}


@dataclass(frozen=True)
class HistoryUpdateResult:
    updated: bool
    reason: str


@dataclass(frozen=True)
class CardEntry:
    game: str
    raw_line: str
    name: str
    quantity: int = 1
    finish: str = "regular"
    condition: str = "NM"
    buy_price: float | None = None


def parse_collection_line(line, game):
    raw_line = str(line or "").strip()
    if not raw_line:
        raise ValueError("line is required")

    card_part, buy_price = _split_buy_price(raw_line)
    quantity, card_part = _split_quantity(card_part)
    condition, card_part = _split_condition(card_part)
    finish, card_part = _split_finish(card_part)

    return CardEntry(
        game=str(game).upper(),
        raw_line=raw_line,
        name=" ".join(card_part.strip().split()),
        quantity=quantity,
        finish=finish,
        condition=condition,
        buy_price=buy_price,
    )


def build_card_line(card_line, quantity=1, finish="regular", buy_price="", condition=""):
    name = " ".join(str(card_line).strip().split())
    if not name:
        raise ValueError("card_line is required")

    parts = []
    if int(quantity or 1) > 1:
        parts.append(f"{int(quantity)}x")
    parts.append(name)

    finish_label = FINISH_LABELS.get(str(finish).lower(), "")
    if finish_label:
        parts.append(f"({finish_label})")

    condition = str(condition or "").strip().upper()
    if condition and condition != "NM":
        parts.append(f"[{condition}]")

    line = " ".join(parts)
    buy_price = str(buy_price or "").strip()
    if buy_price:
        line = f"{line} | {float(buy_price):.2f}"
    return line


def card_identity(game, raw_line):
    normalized = f"{str(game or '').upper()}|{' '.join(str(raw_line or '').lower().split())}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def adjusted_price(price, condition="NM"):
    if price in (None, "", "N/A"):
        return None
    multiplier = CONDITION_MULTIPLIERS.get(str(condition or "NM").upper(), 1.0)
    return round(float(price) * multiplier, 2)


def _split_buy_price(line):
    if "|" not in line:
        return line, None

    card_part, buy_part = line.split("|", 1)
    buy_part = buy_part.strip()
    if not buy_part:
        return card_part.strip(), None
    return card_part.strip(), float(buy_part)


def _split_quantity(line):
    match = re.match(r"^(\d+)x\s+(.+)$", line.strip(), flags=re.IGNORECASE)
    if not match:
        return 1, line.strip()
    return int(match.group(1)), match.group(2).strip()


def _split_finish(line):
    finish = "regular"
    match = re.search(r"\s*\(([^)]*(?:foil|etched)[^)]*)\)", line, flags=re.IGNORECASE)
    if match:
        finish = "etched" if "etched" in match.group(1).lower() else "foil"
        line = f"{line[: match.start()]} {line[match.end():]}".strip()
    return finish, " ".join(line.split())


def _split_condition(line):
    match = re.search(r"\s*\[([A-Za-z]+)\]\s*$", line)
    if not match:
        return "NM", line.strip()
    return match.group(1).upper(), line[: match.start()].strip()


def safe_html(value):
    return html.escape(str(value or ""), quote=True)


def get_refresh_status(last_updated, today=None, stale_after_days=2):
    today = today or date.today()
    if not last_updated:
        return {"state": "missing", "days_old": None}

    updated_on = datetime.strptime(last_updated, "%Y-%m-%d").date()
    days_old = (today - updated_on).days
    state = "stale" if days_old > stale_after_days else "ok"
    return {"state": state, "days_old": days_old}


def update_history(
    history_path,
    total_value,
    today=None,
    failed_cards=0,
    total_cards=0,
    max_failure_rate=0.0,
):
    history_path = Path(history_path)
    today = today or date.today()
    total_cards = int(total_cards or 0)
    failed_cards = int(failed_cards or 0)

    if total_cards > 0:
        failure_rate = failed_cards / total_cards
        if failure_rate > max_failure_rate:
            return HistoryUpdateResult(
                updated=False,
                reason=f"Skipped history update: failure rate {failure_rate:.0%}",
            )

    rows = _read_history_rows(history_path)
    today_key = today.isoformat()
    value = f"{float(total_value):.2f}"

    replaced = False
    for row in rows:
        if row and row[0] == today_key:
            row[1] = value
            replaced = True
            break

    if not replaced:
        rows.append([today_key, value])

    rows.sort(key=lambda row: row[0])
    _write_history_rows(history_path, rows)
    return HistoryUpdateResult(updated=True, reason="history updated")


def _read_history_rows(history_path):
    if not history_path.exists():
        return []

    with history_path.open("r", newline="", encoding="utf-8") as file:
        return [row for row in csv.reader(file) if len(row) >= 2]


def _write_history_rows(history_path, rows):
    history_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    temp_path = history_path.with_suffix(history_path.suffix + ".tmp")
    temp_path.write_bytes(buffer.getvalue().encode("utf-8"))
    os.replace(temp_path, history_path)
