"""Send a short message to a Discord (or Slack-style) webhook when a step fails.

The webhook URL is a secret. It is read from ALERT_WEBHOOK_URL and is never logged.
If the variable is empty, nothing is sent. An alert must never crash the pipeline.
"""

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)


def send_alert(text: str) -> bool:
    """Return True if the message was sent."""
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        log.info("ALERT_WEBHOOK_URL is not set, so no alert was sent")
        return False
    request = urllib.request.Request(
        url,
        data=json.dumps({"content": text[:1900]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "stylehub-pipeline"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return True
    except Exception as exc:  # noqa: BLE001 - an alert problem must not hide the real error
        log.warning("Could not send the alert (%s)", type(exc).__name__)
        return False
