"""The steps every ingestion has in common: check the schema, then write to Raw (or just count).

A source (today: the CSV tables) only has to say HOW to get its DataFrame.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from stylehub.common.config import load_env
from stylehub.common.dates import valid_date
from stylehub.ingestion.raw_writer import write_raw
from stylehub.ingestion.schema_check import OnChange, enforce_schema

log = logging.getLogger(__name__)

# The sources have no updated_at, so every run copies the source AS IT IS NOW. `data_date` is only
# the label of the Raw folder (date=...), it does not select old data. A label older than this
# many days therefore holds today's data under an old name.
MAX_LABEL_AGE_DAYS = 3


def warn_if_backdated(data_date: str, today: date | None = None) -> bool:
    """Log a warning and return True when data_date is older than MAX_LABEL_AGE_DAYS."""
    today = today or datetime.now(UTC).date()
    age_days = (today - date.fromisoformat(data_date)).days
    if age_days <= MAX_LABEL_AGE_DAYS:
        return False
    log.warning(
        "data_date %s is %d days old, but the source is read as it is TODAY. The Raw folder "
        "date=%s will hold today's data, not the data of that day.",
        data_date,
        age_days,
        data_date,
    )
    return True


@dataclass(frozen=True)
class IngestResult:
    """What one ingestion did. str(result) is the sentence for the log."""

    table: str
    data_date: str
    rows: int
    mode: str
    seconds: float
    uri: str | None = None  # None in a dry run: nothing was written

    def __str__(self) -> str:
        head = f"{self.table} {self.data_date}: {self.rows} rows"
        if self.uri is None:
            return f"{head} ({self.mode}, {self.seconds:.1f}s, dry run, nothing written)"
        return f"{head} ({self.mode}, {self.seconds:.1f}s) -> {self.uri}"


def run_ingest(
    table: str,
    data_date: str,
    extract: Callable[[], pd.DataFrame],
    source: str,
    mode: str,
    dry_run: bool = False,
    on_schema_change: OnChange = "fail",
) -> IngestResult:
    """Extract one table. With dry_run, only count the rows and write nothing to GCS."""
    valid_date(data_date)  # before anything is read or written
    warn_if_backdated(data_date)
    load_env()
    started = time.perf_counter()
    df = enforce_schema(extract(), table, on_schema_change)

    if dry_run:
        seconds = time.perf_counter() - started
        return IngestResult(table, data_date, len(df), mode, seconds)
    uri = write_raw(df, table, data_date, source=source)
    seconds = time.perf_counter() - started
    return IngestResult(table, data_date, len(df), mode, seconds, uri)
