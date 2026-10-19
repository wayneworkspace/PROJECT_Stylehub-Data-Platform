"""Fail and alert when a daily Bronze table was not loaded recently."""

from datetime import UTC, datetime
from importlib import import_module

get_logger = import_module("src.0_utils.logger").get_logger
alerts = import_module("src.0_utils.alerts")
bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")
runs = import_module("src.3_storage.runs")

log = get_logger(__name__)

STALE_AFTER_HOURS = 26  # a daily load plus a little room
SQL_FILE = config.SQL_DIR / "serving" / "02_data_freshness.sql"


def stale_tables(rows: list[tuple[str, int]]) -> list[str]:
    """Names of tables older than STALE_AFTER_HOURS, from (name, hours_old)."""
    return [f"{name} ({hours} h)" for name, hours in rows if hours > STALE_AFTER_HOURS]


def check(data_date: str, run_id: str) -> None:
    """Record a freshness step; alert and raise when any table is stale."""
    cfg = config.settings()
    started = datetime.now(UTC)
    sql = bq.render_sql(SQL_FILE, cfg)
    client = config.bq_client(cfg)
    job = retry.call_with_retry(lambda: client.query(sql, job_config=bq.query_config(cfg)).result())
    rows = [(r.table_name, r.hours_old) for r in job]
    stale = stale_tables(rows)
    error = f"stale Bronze tables: {', '.join(stale)}" if stale else None
    status = "failed" if stale else "success"
    finished = datetime.now(UTC)
    detail = {"hours_old": dict(rows)}
    runs.record_run(
        run_id, "freshness", data_date, status, started, finished, None, error, detail, cfg
    )
    if stale:
        alerts.send_alert(f":warning: **stylehub_daily** {run_id}: {error}")
        raise RuntimeError(error)
    log.info("[run %s] all %d Bronze tables are fresh", run_id, len(rows))
