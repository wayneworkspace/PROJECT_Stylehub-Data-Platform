"""Record one row per pipeline step in BigQuery (table: <ops dataset>.pipeline_runs).

Recording is best effort: if it fails, the error is logged and the pipeline goes on.
"""

import json
import logging
from datetime import date, datetime
from functools import cache
from typing import Any, TypedDict

from google.cloud import bigquery

from stylehub.common.clients import bq_client
from stylehub.common.config import SQL_DIR, Settings, resolve
from stylehub.common.retry import call_with_retry
from stylehub.common.sql import render_sql

log = logging.getLogger(__name__)


class RunRow(TypedDict):
    """One row of pipeline_runs (see src/stylehub/sql/ops/01_pipeline_runs.sql)."""

    run_id: str
    step: str
    data_date: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    rows_loaded: int | None
    error: str | None
    detail: str | None  # JSON: rows per table, dbt test counts, ...


@cache
def _runs_client(cfg: Settings) -> bigquery.Client:
    """Build the BigQuery client and create pipeline_runs, once per process."""
    client = bq_client(cfg)
    sql = render_sql(SQL_DIR / "ops" / "01_pipeline_runs.sql", cfg)
    call_with_retry(lambda: client.query(sql).result())
    return client


def run_row(
    run_id: str,
    step: str,
    data_date: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    rows_loaded: int | None = None,
    error: str | None = None,
    detail: dict[str, Any] | None = None,
) -> RunRow:
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
        "detail": json.dumps(detail, sort_keys=True) if detail else None,
    }


def record_run(row: RunRow, cfg: Settings | None = None) -> bool:
    """Append one row to pipeline_runs. Return True on success, False (and a warning) if not."""
    try:
        cfg = resolve(cfg)
        client = _runs_client(cfg)
        table = f"{cfg.project}.{cfg.ops}.pipeline_runs"
        # A load job (not a streaming insert) also works without billing.
        call_with_retry(lambda: client.load_table_from_json([dict(row)], table).result())
    except Exception as exc:  # recording must not break the pipeline
        log.warning("Could not record the run in BigQuery: %s", exc)
        return False
    return True
