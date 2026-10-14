"""Record one row per pipeline step in BigQuery (table: <ops dataset>.pipeline_runs).

Recording is best effort: if it fails, the pipeline still goes on and the error is logged.
A row that cannot be saved is NOT lost. It is appended to logs/pipeline_runs_pending.jsonl and
sent together with the next row that is saved. (Inside a throwaway container the file goes away
with the container. Airflow and local runs keep it, because logs/ is in the project folder.)
"""

import json
import logging
from datetime import date, datetime
from functools import cache

from google.cloud import bigquery

from common.config import PENDING_RUNS_FILE, SQL_DIR, Settings, render_sql, settings
from common.retry import call_with_retry

log = logging.getLogger(__name__)


@cache
def _runs_client(cfg: Settings) -> bigquery.Client:
    """Build the BigQuery client and create pipeline_runs, once per process.

    @cache keeps the first result, so the next steps skip the CREATE TABLE query.
    If this raises, nothing is cached and the next step tries again.
    """
    client = bigquery.Client(project=cfg.project)
    sql = render_sql(SQL_DIR / "ops" / "01_pipeline_runs.sql")
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
) -> dict[str, object]:
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


def read_pending() -> list[dict]:
    """Rows that an earlier run could not save. A damaged line is skipped, not fatal."""
    try:
        lines = PENDING_RUNS_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            log.warning("Skipping a damaged line in %s", PENDING_RUNS_FILE.name)
    return rows


def save_pending(row: dict) -> None:
    try:
        PENDING_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with PENDING_RUNS_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row) + "\n")
    except OSError as exc:  # the last safety net must not crash the pipeline either
        log.warning("Could not keep the run row in %s: %s", PENDING_RUNS_FILE.name, exc)


def record_run(row: dict) -> bool:
    """Append one row (and any waiting rows) to pipeline_runs. Return True on success."""
    rows = read_pending() + [row]
    try:
        cfg = settings()
        client = _runs_client(cfg)
        table = f"{cfg.project}.{cfg.ops}.pipeline_runs"
        # A load job is used (not streaming inserts), so it also works without billing.
        call_with_retry(lambda: client.load_table_from_json(rows, table).result())
    except Exception as exc:  # noqa: BLE001 - recording must not break the pipeline
        log.warning("Could not record the run in BigQuery, keeping it for later: %s", exc)
        save_pending(row)
        return False
    try:
        PENDING_RUNS_FILE.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Could not remove %s: %s", PENDING_RUNS_FILE.name, exc)
    return True
