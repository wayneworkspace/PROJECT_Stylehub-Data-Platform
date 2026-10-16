# ruff: noqa: S608  (the SQL below is built from our settings and constants, never from a user)

"""Alert when the pipeline has not finished a run lately (the "did not run" alert).

Airflow cannot tell you that Airflow itself is down. So run this from somewhere else, for example
the GitHub Actions schedule in .github/workflows/freshness.yaml. It checks two things and uses
the OLDER of the two, so a green check needs both:
1. pipeline_runs: the newest data date for which ALL four steps (ingest, bronze, silver, gold)
   succeeded. A hand-run `gold` alone no longer makes the check green.
2. the data itself: the oldest `max(_ingested_at)` of the four Bronze tables.

Usage: python -m stylehub.orchestration.check_freshness [--max-age-hours 26]
Exit code 0 = fresh. Exit code 1 = stale or no run found: an alert is sent to ALERT_WEBHOOK_URL.
"""

import argparse
import logging
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from stylehub.common.bq import query_config
from stylehub.common.config import Settings, resolve
from stylehub.common.logs import setup_cli_logging
from stylehub.common.retry import call_with_retry
from stylehub.orchestration.alerts import send_alert

log = logging.getLogger(__name__)

DEFAULT_MAX_AGE_HOURS = 26  # a daily run, plus two hours of slack
STEP_NAMES = ("ingest", "bronze", "silver", "gold")
BRONZE_TABLES = ("orders", "order_items", "products", "users")  # events is built once


def hours_since(last_finished: datetime | None, now: datetime) -> float | None:
    """How many hours ago the last good run ended. None when there is no such run."""
    if last_finished is None:
        return None
    return (now - last_finished).total_seconds() / 3600


def is_stale(last_finished: datetime | None, now: datetime, max_age_hours: float) -> bool:
    """True when there is no good run, or the newest one is older than the limit."""
    age = hours_since(last_finished, now)
    return age is None or age > max_age_hours


def run_query(client: bigquery.Client, query: str) -> list[bigquery.Row]:
    return list(call_with_retry(lambda: client.query(query, job_config=query_config()).result()))


def last_complete_run(
    client: bigquery.Client | None = None, cfg: Settings | None = None
) -> datetime | None:
    """When the newest data date finished with ALL steps successful, or None.

    Grouped by data date, not by run id: the cron setup runs ingest and the rest on two machines
    (two run ids), the Airflow setup on one. Pass `client` to use your own BigQuery client.
    """
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
    steps = ", ".join(f"'{name}'" for name in STEP_NAMES)
    # Names come from our settings and constants, never from a user.
    query = (
        "WITH ok AS ("
        " SELECT data_date, COUNT(DISTINCT step) AS n_steps, MAX(finished_at) AS finished_at"
        f" FROM `{cfg.project}.{cfg.ops}.pipeline_runs`"
        f" WHERE status = 'success' AND step IN ({steps}) GROUP BY data_date) "
        f"SELECT MAX(finished_at) AS last_finished FROM ok WHERE n_steps = {len(STEP_NAMES)}"
    )
    try:
        rows = run_query(client, query)
    except NotFound:
        return None
    return rows[0].last_finished


def last_bronze_load(
    client: bigquery.Client | None = None, cfg: Settings | None = None
) -> datetime | None:
    """The oldest "newest _ingested_at" of the Bronze tables, or None if one is empty or missing.

    This looks at the data, not at the log: one table that stopped loading makes it old.
    Pass `client` to use your own BigQuery client.
    """
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
    newest: list[datetime] = []
    for table in BRONZE_TABLES:
        query = f"SELECT MAX(_ingested_at) AS d FROM `{cfg.project}.{cfg.bronze}.{table}`"
        try:
            value = run_query(client, query)[0].d
        except NotFound:
            return None
        if value is None:
            return None
        newest.append(value)
    return min(newest)


def last_success() -> datetime | None:
    """The older of: the last complete run and the last Bronze load. None = nothing to trust."""
    run, load = last_complete_run(), last_bronze_load()
    if run is None or load is None:
        return None
    return min(run, load)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    args = parser.parse_args()
    setup_cli_logging()

    now = datetime.now(UTC)
    last = last_success()
    if not is_stale(last, now, args.max_age_hours):
        log.info("OK: the last good run ended %.1f hours ago", hours_since(last, now))
        return 0
    if last is None:
        when = "no successful run found"
    else:
        when = f"last good run ended {last:%Y-%m-%d %H:%M} UTC"
    message = f"StyleHub pipeline DID NOT RUN in the last {args.max_age_hours:g} hours\n{when}"
    log.error("%s", message)
    send_alert(message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
