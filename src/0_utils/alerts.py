"""Short alerts to the team chat (Discord webhook); never raises."""

import os
from importlib import import_module

import requests

get_logger = import_module("src.0_utils.logger").get_logger

log = get_logger(__name__)

MAX_CHARS = 1900  # Discord allows 2000 characters per message


def failure_message(
    dag_id: str, task_id: str | None, run_id: str, error: str, log_url: str | None
) -> str:
    """One readable alert for a failed task or DAG run."""
    what = f"task `{task_id}`" if task_id else "the DAG run"
    lines = [f":red_circle: **{dag_id}**: {what} failed", f"Run: `{run_id}`", f"Error: {error}"]
    if log_url:
        lines.append(f"Log: {log_url}")
    return "\n".join(lines)


def send_alert(text: str) -> bool:
    """Post text to ALERT_WEBHOOK_URL; False when unset or the post fails."""
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        log.warning("ALERT_WEBHOOK_URL is not set; alert not sent: %s", text[:200])
        return False
    try:
        response = requests.post(url, json={"content": text[:MAX_CHARS]}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:  # an alert must never break the pipeline
        log.warning("Could not send the alert: %s", type(exc).__name__)
        return False
    return True
