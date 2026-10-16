"""Small BigQuery helpers that more than one step needs."""

from collections.abc import Callable
from typing import Any

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery

from stylehub.common.config import Settings, resolve
from stylehub.common.retry import call_with_retry


def query_config(cfg: Settings | None = None, **options: object) -> bigquery.QueryJobConfig:
    """A query config with the cost limit (BQ_MAX_BYTES_BILLED). Pass dry_run=True and so on."""
    return bigquery.QueryJobConfig(maximum_bytes_billed=resolve(cfg).max_bytes_billed, **options)


def table_exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        call_with_retry(lambda: client.get_table(table_id))
    except NotFound:
        return False
    return True


MAX_JOB_TRIES = 5  # ids tried for one load: <id>, <id>_r1, <id>_r2, ...


def job_has_failed(job: bigquery.job.LoadJob | bigquery.job.CopyJob) -> bool:
    """True when BigQuery finished the job and it ended with an error."""
    return job.state == "DONE" and job.error_result is not None


def load_job_once[JobT: (bigquery.job.LoadJob, bigquery.job.CopyJob)](
    client: bigquery.Client,
    start_job: Callable[[str], JobT],
    job_id: str,
    location: str | None = None,
) -> JobT:
    """Start a load (or copy) job with a fixed id, wait for it, and return the finished job.

    Make the id ONCE per load and keep it the same on every retry. If an earlier try reached
    BigQuery but the answer was lost (a timeout), BigQuery refuses a second job with the same id
    (409 Conflict). Then we wait for the job that is already there, so the rows are loaded once.

    If that job already FAILED, waiting for it would only give the same error again. A failed
    load wrote nothing, so it is safe to start a new job. The new id is made from the old one
    (<id>_r1, <id>_r2, ...), so every retry of the same load still maps to the same job.
    """
    for attempt in range(MAX_JOB_TRIES):
        current = job_id if attempt == 0 else f"{job_id}_r{attempt}"
        job: Any
        try:
            job = start_job(current)
        except Conflict:
            job = client.get_job(current, location=location)
            if job_has_failed(job):
                continue
        job.result()
        return job
    raise RuntimeError(f"load job {job_id} failed {MAX_JOB_TRIES} times in BigQuery")
