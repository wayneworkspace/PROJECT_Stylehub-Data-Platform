"""Record one row per pipeline step in BigQuery (table: <ops dataset>.pipeline_runs).

Recording is best effort: if it fails, the pipeline still goes on and the error is logged.
A row that cannot be saved is NOT lost. It is appended to logs/pipeline_runs_pending.jsonl and
sent together with the next row that is saved. (Inside a throwaway container the file goes away
with the container. Airflow keeps it in a volume, local runs in the project folder.)

Two processes can run at the same time, so the waiting file is never read and then deleted:
a process first RENAMES it to its own name (one step, nobody else can take the same rows), sends
the rows, and only then removes its file. A row written meanwhile goes to a fresh pending file.
The BigQuery job id is made from the rows themselves, so if a file is sent twice (a crash between
the load and the delete) BigQuery refuses the second job and the rows are not stored twice.
"""

import contextlib
import hashlib
import json
import logging
import uuid
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any, TypedDict

from google.cloud import bigquery

from stylehub.common.bq import load_job_once
from stylehub.common.config import PENDING_RUNS_FILE, SQL_DIR, Settings, resolve
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
    """Build the BigQuery client and create pipeline_runs, once per process.

    @cache keeps the first result, so the next steps skip the CREATE TABLE query.
    If this raises, nothing is cached and the next step tries again.
    """
    client = bigquery.Client(project=cfg.project)
    # Only the CREATE (01). The migrations (02, ...) are run by setup.setup_gcp.
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


CLAIMED_SUFFIX = ".claimed"


def read_rows(path: Path) -> list[RunRow]:
    """The rows in one pending file. A damaged line is skipped, not fatal."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows: list[RunRow] = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            log.warning("Skipping a damaged line in %s", path.name)
    return rows


def read_pending() -> list[RunRow]:
    """Rows that an earlier run could not save."""
    return read_rows(PENDING_RUNS_FILE)


def claim_pending() -> list[Path]:
    """Take the waiting rows for this process. Return the files that now belong to it.

    The rename is one step, so two processes can never take the same file. Files that an earlier
    process claimed and then died on are taken too.
    """
    claimed_name = f"{PENDING_RUNS_FILE.name}.{uuid.uuid4().hex}{CLAIMED_SUFFIX}"
    mine = PENDING_RUNS_FILE.with_name(claimed_name)
    with contextlib.suppress(FileNotFoundError):
        PENDING_RUNS_FILE.replace(mine)
    return sorted(PENDING_RUNS_FILE.parent.glob(f"{PENDING_RUNS_FILE.name}.*{CLAIMED_SUFFIX}"))


def run_job_id(rows: list[RunRow]) -> str:
    """The same rows always give the same BigQuery job id (a repeated send is refused)."""
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()
    return f"pipeline_runs_{digest[:32]}"


def save_pending(row: RunRow) -> None:
    try:
        PENDING_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with PENDING_RUNS_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row) + "\n")
    except OSError as exc:  # the last safety net must not crash the pipeline either
        log.warning("Could not keep the run row in %s: %s", PENDING_RUNS_FILE.name, exc)


def record_run(row: RunRow, cfg: Settings | None = None) -> bool:
    """Append one row (and any waiting rows) to pipeline_runs. Return True on success."""
    try:
        claimed = claim_pending()
    except OSError as exc:  # for example a locked file on Windows: recording must not crash a step
        log.warning("Could not take the waiting rows, keeping this one for later: %s", exc)
        save_pending(row)
        return False
    waiting = [r for path in claimed for r in read_rows(path)]
    rows = [*waiting, row]
    try:
        cfg = resolve(cfg)
        client = _runs_client(cfg)
        table = f"{cfg.project}.{cfg.ops}.pipeline_runs"
        # A load job is used (not streaming inserts), so it also works without billing.
        # One job id for all tries, made from the rows: a retry after a lost answer, or a second
        # send of the same file, must not add the rows twice.
        job_id = run_job_id(rows)
        json_rows = [dict(r) for r in rows]
        call_with_retry(
            lambda: load_job_once(
                client,
                lambda jid: client.load_table_from_json(json_rows, table, job_id=jid),
                job_id,
                cfg.location,
            )
        )
    except Exception as exc:  # recording must not break the pipeline
        log.warning("Could not record the run in BigQuery, keeping it for later: %s", exc)
        for kept in [*waiting, row]:  # put everything back in the shared pending file
            save_pending(kept)
        remove_files(claimed)
        return False
    remove_files(claimed)
    return True


def remove_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not remove %s: %s", path.name, exc)
