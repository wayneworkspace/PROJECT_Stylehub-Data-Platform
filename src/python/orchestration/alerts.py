"""Send a short message to a Discord (or Slack-style) webhook when a step fails.

The webhook URL is a secret. It is read from ALERT_WEBHOOK_URL and is never logged.
If the variable is empty, nothing is sent. An alert must never crash the pipeline.
"""

import json
import logging
import urllib.request

from common.config import alert_webhook_url

log = logging.getLogger(__name__)

DISCORD_MAX_CHARS = 1900  # Discord rejects messages over 2000 characters. Keep a safety margin.
REQUEST_TIMEOUT_SECONDS = 10  # A slow webhook must not hold up the pipeline.


def send_alert(text: str) -> bool:
    """Return True if the message was sent."""
    url = alert_webhook_url()
    if not url:
        log.info("ALERT_WEBHOOK_URL is not set, so no alert was sent")
        return False
    request = urllib.request.Request(
        url,
        data=json.dumps({"content": text[:DISCORD_MAX_CHARS]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "stylehub-pipeline"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS):
            return True
    except Exception as exc:  # noqa: BLE001 - an alert problem must not hide the real error
        log.warning("Could not send the alert (%s)", type(exc).__name__)
        return False
