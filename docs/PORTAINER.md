# Portainer Deployment

## Git Stack

1. In Portainer, create a new stack from a Git repository.
2. Use this repository URL and select `compose.yml` as the Compose path.
3. Add any optional environment values from `.env.example` in Portainer.
4. Deploy the stack and wait for the `tcg-tracker` container to become healthy.
5. Open `http://<docker-host>:8084/`.

The stack stores installation-specific files in `./data`, mounted at `/data` inside the container. The source tree and personal collection data remain separate.

## Data Directory

The container runs as user ID `1000`. On a Linux Docker host, create the data directory in the stack working directory and make it writable by that user:

```bash
mkdir -p data
chown -R 1000:1000 data
```

Optional starter files are available in `examples/`:

```bash
cp examples/my_cards.example.txt data/my_cards.txt
cp examples/wishlist.example.txt data/wishlist.txt
```

You can also start empty and add collection cards from the web interface.

## Health Check

Portainer should report the container as healthy after this endpoint responds:

```text
GET /health
```

## Scheduled Refresh

The dashboard refresh button updates collection and wishlist prices. For the full report pipeline, schedule this command on the Docker host:

```bash
docker exec tcg-tracker python price_tracker.py
```

The full pipeline updates the Excel export, standalone report, collection history, per-card history, movers, wishlist cache, and optional Discord alerts.

## Updating

Pull the latest repository revision and redeploy the stack with a fresh build. The `data` directory is not part of the image and should remain in place across upgrades.

## Backup

Back up the stack's `data` directory. It contains the collection, wishlist, history, alert cooldown state, caches, and generated exports.

## Rollback

Keep the previous image or stack revision available. If a new deployment does not pass its health check, redeploy the previous revision and inspect the container logs before retrying.

## Network Safety

This app has collection-changing endpoints and no built-in user accounts. Keep it on a trusted network, behind a VPN, or behind an authenticated reverse proxy. Do not publish port `8084` directly to the internet.
