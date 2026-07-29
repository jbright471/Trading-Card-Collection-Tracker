# Multi TCG Tracker

A self-hosted collection and price tracker for Magic: The Gathering, Yu-Gi-Oh!, and Pokemon cards. It includes a responsive light/dark dashboard, collection management, portfolio analytics, wishlist targets, transactions, imports, and backups.

## Features

- Track MTG, Yu-Gi-Oh!, and Pokemon cards in one collection.
- View collection value, profit/loss, data freshness, and price history.
- Browse a responsive card gallery with card art, set, finish, condition, quantity, and value.
- Search supported card databases and add cards from the web interface.
- Open any card for a larger image, per-card history, source details, editing, sales, or archival.
- Watch and manage wishlist targets with current prices, progress, alert controls, and deal indicators.
- Record purchases, partial or complete sales, fees, shipping, and realized profit/loss.
- Review daily movers, value allocation, concentration, provider failures, and suspicious history points.
- Preview and import common collection CSV exports without replacing existing cards.
- Download portable backups, restore safely, and keep rotating daily backups in `data/backups`.
- Refresh in the background with progress, API pacing, retry, rate-limit backoff, and a cross-process lock.
- Keep last-known values when individual lookups fail.
- Skip portfolio-history writes whenever a provider lookup fails.
- Track price source, currency, finish, freshness, and transparent condition-adjusted estimates.
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

Condition valuations are estimates based on the provider market price: M 105%, NM 100%, LP 85%, MP 70%, HP 50%, and damaged 30%. The card detail drawer shows both the provider market price and the adjusted estimate.

For compatibility, the web app also reads separate `mtg_cards.txt`, `ygo_cards.txt`, and `pkm_cards.txt` files when `my_cards.txt` does not exist.

## Wishlist Format

Create `data/wishlist.txt` with one target per line:

```text
Lightning Bolt #150 | < 2.00
[YGO] Dark Magician | <= 10.00
[PKM] Pikachu #base1-58 | < 20.00
```

Supported operators are `<`, `<=`, `>`, and `>=`. Targets can also be added, edited, muted, and removed from the dashboard.

## Collection Management

Select any tracked card to open its detail drawer. From there you can:

- Edit quantity, condition, finish, name/ID, and purchase price.
- Review per-card price history and provider metadata.
- Record a partial or complete sale with fees and shipping.
- Archive a card without recording a sale or permanently delete it.

Sales and purchases appear under **Data > Activity**. Realized and unrealized profit remain separate.

## Import And Backup

The **Data > Import & Backup** view previews CSV rows before importing them. It recognizes common headings such as card name, product line, collector number, quantity, printing, condition, and price paid.

The backup ZIP contains collection and wishlist files, histories, transactions, caches, and preferences. It does not contain environment variables, webhook URLs, PINs, or other secrets. A daily rotating backup is also written under the mounted `data/backups` directory.

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
| `TCG_TRACKER_PIN` | empty | Optional PIN required for collection-changing actions and private downloads. |
| `TCG_TRACKER_SECRET_KEY` | derived locally | Stable session key; set a long random value when using a PIN with multiple containers. |

## Data Privacy

Collection files, wishlist files, caches, exports, charts, and generated reports are ignored by Git. Only harmless example files are included in this repository. Docker also excludes local collection data from the image build context.

An optional PIN protects collection-changing actions and private downloads. It is still best to keep the app on a trusted local network or access it through an authenticated reverse proxy or VPN; do not publish it directly to the internet.

## Project Layout

| Path | Purpose |
| --- | --- |
| `app.py` | Main Flask web application. |
| `tcg_tracker/` | Dashboard storage, parsing, search, and refresh logic. |
| `tcg/` | Scheduled report, history, wishlist, and notification pipeline. |
| `templates/`, `static/` | Responsive dashboard, card manager, data tools, and add-card interface. |
| `examples/` | Safe starter collection and wishlist files. |
| `tests/` | Offline unit and route tests. |
| `Dockerfile`, `compose.yml` | Docker and Portainer deployment. |

Price data comes from Scryfall, YGOPRODeck, and TCGdex. Availability and market coverage depend on those services.
