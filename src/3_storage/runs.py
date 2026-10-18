"""Record one pipeline_runs row per step; failures only log warnings."""

import json
from datetime import datetime
from importlib import import_module
from typing import Any

from src.utils.logger import get_logger

config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")

log = get_logger(__name__)


def record_run(
    run_id: str,
    step: str,
    data_date: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    rows_loaded: int | None,
    error: str | None,
    detail: dict[str, Any] | None,
    cfg: config.Settings,
) -> None:
    """Append one row to pipeline_runs (table defined in infra/terraform/main.tf)."""
    row = {
        "run_id": run_id,
        "step": step,
        "data_date": data_date,
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "rows_loaded": rows_loaded,
        "error": error,
        "detail": json.dumps(detail, sort_keys=True) if detail else None,  # rows, dbt counts
    }
    try:
        client = config.bq_client(cfg)
        table = f"{cfg.project}.{cfg.ops}.pipeline_runs"
        # Load job, not streaming insert, so it works without billing.
        retry.call_with_retry(lambda: client.load_table_from_json([row], table).result())
    except Exception as exc:  # recording must not break the pipeline
        log.warning("Could not record the run in BigQuery: %s", exc)
