"""Alert when the pipeline has not finished a run lately (the "did not run" alert).

Airflow cannot tell you that Airflow itself is down. So run this from somewhere else, for example
the GitHub Actions schedule in .github/workflows/freshness.yaml. It reads pipeline_runs, finds the
newest successful `gold` step (the last step of a full run) and compares its age with the limit.

Usage: python -m orchestration.check_freshness [--max-age-hours 26]
Exit code 0 = fresh. Exit code 1 = stale or no run found: an alert is sent to ALERT_WEBHOOK_URL.
"""

import argparse
import logging
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from common.config import settings
from common.retry import call_with_retry
from orchestration.alerts import send_alert

log = logging.getLogger(__name__)

DEFAULT_MAX_AGE_HOURS = 26  # a daily run, plus two hours of slack


def hours_since(last_finished: datetime | None, now: datetime) -> float | None:
    """How many hours ago the last good run ended. None when there is no such run."""
    if last_finished is None:
        return None
    return (now - last_finished).total_seconds() / 3600


def is_stale(last_finished: datetime | None, now: datetime, max_age_hours: float) -> bool:
    """True when there is no good run, or the newest one is older than the limit."""
    age = hours_since(last_finished, now)
    return age is None or age > max_age_hours


def last_success() -> datetime | None:
    """The end time of the newest successful gold step, or None (also when the table is missing)."""
    cfg = settings()
    client = bigquery.Client(project=cfg.project)
    query = (
        f"SELECT MAX(finished_at) AS last_finished FROM `{cfg.project}.{cfg.ops}.pipeline_runs` "
        "WHERE step = 'gold' AND status = 'success'"
    )
    try:
        rows = call_with_retry(lambda: client.query(query).result())
    except NotFound:
        return None
    return next(iter(rows)).last_finished


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    args = parser.parse_args()

    now = datetime.now(UTC)
    last = last_success()
    if not is_stale(last, now, args.max_age_hours):
        print(f"OK: the last good run ended {hours_since(last, now):.1f} hours ago")
        return 0
    if last is None:
        when = "no successful run found"
    else:
        when = f"last good run ended {last:%Y-%m-%d %H:%M} UTC"
    message = f"StyleHub pipeline DID NOT RUN in the last {args.max_age_hours:g} hours\n{when}"
    print(message)
    send_alert(message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
