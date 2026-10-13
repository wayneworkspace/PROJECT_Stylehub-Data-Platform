"""Record one row per pipeline step in BigQuery (table: <ops dataset>.pipeline_runs).

Recording is best effort. If it fails, the pipeline still goes on and the error is logged.
"""

import logging
from datetime import date, datetime

from google.cloud import bigquery

from pipeline.config import SQL_DIR, render_sql, settings

log = logging.getLogger(__name__)


def run_row(
    run_id: str,
    step: str,
    data_date: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    rows_loaded: int | None = None,
    error: str | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "step": step,
        "data_date": date.fromisoformat(data_date).isoformat(),
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "rows_loaded": rows_loaded,
        "error": error,
    }


def record_run(row: dict) -> bool:
    """Create the table if needed, then append one row. Return True on success."""
    try:
        s = settings()
        client = bigquery.Client(project=s["project"])
        client.query(render_sql(SQL_DIR / "ops" / "01_pipeline_runs.sql")).result()
        # A load job is used (not streaming inserts), so it also works without billing.
        client.load_table_from_json(
            [row], f"{s['project']}.{s['ops']}.pipeline_runs"
        ).result()
        return True
    except Exception as exc:  # noqa: BLE001 - recording must not break the pipeline
        log.warning("Could not record the run in BigQuery: %s", exc)
        return False
