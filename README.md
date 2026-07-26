# Multi TCG Tracker

A self-hosted collection and price tracker for Magic: The Gathering, Yu-Gi-Oh!, and Pokemon cards. It includes a responsive light/dark dashboard, card images, portfolio history, wishlist targets, and a searchable add-card workflow.

## Features

- Track MTG, Yu-Gi-Oh!, and Pokemon cards in one collection.
- View collection value, profit/loss, data freshness, and price history.
- Browse a responsive card gallery with card art, set, finish, condition, quantity, and value.
- Search supported card databases and add cards from the web interface.
- Watch wishlist targets with current prices, card images, and deal indicators.
- Refresh from the dashboard with API pacing, retry, and rate-limit backoff.
- Keep last-known values when individual lookups fail.
- Skip bad history snapshots when too many lookups fail.
- Generate an Excel export and a standalone HTML report.
- Track per-card history, daily movers, gainers, and losers.
- Send optional Discord value and wishlist deal alerts.
- Run locally, with Docker Compose, or as a Portainer stack.

## Quick Start

Requirements: Python 3.10 or newer.

```powershell
git clone https://github.com/jbright471/Trading-Card-Collection-Tracker.git
cd Trading-Card-Collection-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force data
Copy-Item examples\my_cards.example.txt data\my_cards.txt
Copy-Item examples\wishlist.example.txt data\wishlist.txt
$env:TCG_TRACKER_DATA_DIR = "$PWD\data"
python app.py
```

Open [http://localhost:8084](http://localhost:8084). Windows users can also run `Run Web App.bat` after installing the requirements.

The dashboard works with an empty `data` folder, so copying the examples is optional.

## Collection Format

The recommended collection file is `data/my_cards.txt`. Lines without a game prefix are treated as MTG cards.

```text
Lightning Bolt #150
2x Sol Ring (Foil) | 1.50
[YGO] Dark Magician
[PKM] Pikachu #base1-58
```

Supported modifiers:

- `2x` sets quantity.
- `(Foil)` or `(Etched)` sets finish.
- `[LP]`, `[MP]`, or another condition follows the card name.
- `| 1.50` records the per-card purchase price.
- `[MTG]`, `[YGO]`, or `[PKM]` selects a game in the unified file.

For compatibility, the web app also reads separate `mtg_cards.txt`, `ygo_cards.txt`, and `pkm_cards.txt` files when `my_cards.txt` does not exist.

## Wishlist Format

Create `data/wishlist.txt` with one target per line:

```text
Lightning Bolt #150 | < 2.00
[YGO] Dark Magician | <= 10.00
[PKM] Pikachu #base1-58 | < 20.00
```

Supported operators are `<`, `<=`, `>`, and `>=`. The dashboard refresh updates wishlist prices and card images along with the collection.

## Docker And Portainer

Create the local data directory, then start the stack:

```powershell
New-Item -ItemType Directory -Force data
docker compose up -d --build
```

The stack publishes port `8084`, mounts `./data` at `/data`, and includes a health check. In Portainer, deploy `compose.yml` as a Git-backed stack or paste its contents into the web editor.

Your Docker host must allow container user `1000` to write to the mounted `data` directory. See [docs/PORTAINER.md](docs/PORTAINER.md) for deployment and scheduling details.

## Refresh Options

The `Refresh Prices` button updates the web dashboard, collection history, and wishlist cache.

The full scheduled refresh also creates the Excel and standalone HTML reports, per-card history, movers, and optional Discord alerts:

```powershell
$env:TCG_TRACKER_DATA_DIR = "$PWD\data"
python price_tracker.py
```

For Docker:

```text
docker exec tcg-tracker python price_tracker.py
```

Run that command from cron, Task Scheduler, or another scheduler at the interval you prefer. A daily run is usually enough for a personal collection.

## Configuration

Copy `.env.example` to `.env` when using Docker Compose, or set the same values in your environment or Portainer stack.

Important settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TCG_TRACKER_DATA_DIR` | `.` | Location for collection and generated data. |
| `DISCORD_WEBHOOK_URL` | empty | Enables optional Discord alerts. |
| `REQUEST_DELAY` | `0.75` | Delay between card lookups. |
| `SCRYFALL_MIN_INTERVAL_SECONDS` | `0.65` | Minimum spacing between Scryfall requests. |
| `HTTP_MAX_RETRIES` | `4` | Retries for rate-limited requests. |
| `WISHLIST_COOLDOWN_DAYS` | `7` | Days between repeat deal alerts. |
| `HISTORY_RETENTION_DAYS` | `90` | Collection history retention window. |

## Data Privacy

Collection files, wishlist files, caches, exports, charts, and generated reports are ignored by Git. Only harmless example files are included in this repository. Docker also excludes local collection data from the image build context.

Do not expose this app directly to the public internet. It is intended for a trusted local network or access through an authenticated reverse proxy or VPN.

## Project Layout

| Path | Purpose |
| --- | --- |
| `app.py` | Main Flask web application. |
| `tcg_tracker/` | Dashboard storage, parsing, search, and refresh logic. |
| `tcg/` | Scheduled report, history, wishlist, and notification pipeline. |
| `templates/`, `static/` | Responsive dashboard and add-card interface. |
| `examples/` | Safe starter collection and wishlist files. |
| `tests/` | Offline unit and route tests. |
| `Dockerfile`, `compose.yml` | Docker and Portainer deployment. |

Price data comes from Scryfall, YGOPRODeck, and TCGdex. Availability and market coverage depend on those services.
