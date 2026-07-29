"""Discord webhook notifications."""
import json
import urllib.error
import urllib.parse
import urllib.request

from tcg.config import DISCORD_WEBHOOK_URL, HTTP_TIMEOUT


def _post(content):
    """POST a message to the configured webhook with a hard timeout."""
    if not DISCORD_WEBHOOK_URL:
        return
    parsed = urllib.parse.urlparse(DISCORD_WEBHOOK_URL)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Discord webhook URL must use HTTPS")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps({"content": content}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)  # nosec B310


def send_value_alert(current_value, percent_change):
    try:
        _post(
            f"🚀 **Collection Value Alert!**\n"
            f"Your collection is now worth **${current_value:.2f}**.\n"
            f"That's a **{percent_change:.1f}%** increase since the last check!"
        )
        print("Discord alert sent!")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        print(f"Failed to send Discord alert: {e}")


def send_deal_alert(deals):
    """Send a single Discord message for all deals that need a fresh alert."""
    if not DISCORD_WEBHOOK_URL:
        return
    alertable = [d for d in deals if d.get('needs_alert')]
    if not alertable:
        return
    lines = ["🎯 **Sniper Alert — Cards hit your target price!**\n"]
    for d in alertable:
        lines.append(
            f"• **{d['data']['name']}** — ${d['current_price']:.2f} "
            f"(target: {d['operator']}${d['target_price']:.2f} · save ${d['savings']:.2f})"
        )
    try:
        _post("\n".join(lines))
        print(f"Deal alert sent for {len(alertable)} card(s).")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        print(f"Failed to send deal alert: {e}")


def send_test_alert():
    if not DISCORD_WEBHOOK_URL:
        return False, "Discord webhook is not configured"
    try:
        _post("TCG Collection Tracker test notification: alerts are connected.")
        return True, "Discord test notification sent"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return False, f"Discord test failed: {exc}"
