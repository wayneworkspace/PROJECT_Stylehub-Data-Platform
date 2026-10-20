"""Incremental load of the StyleHub API users into the Raw Zone."""

import time
from datetime import date, datetime, timedelta
from importlib import import_module

import pandas as pd
import pyarrow as pa

get_logger = import_module("src.0_utils.logger").get_logger

api = import_module("src.1_source.api")
bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
raw_writer = import_module("src.2_ingestion.raw_writer")
schema_check = import_module("src.2_ingestion.schema_check")

log = get_logger(__name__)

TABLE = "api_users"
ENDPOINT = "/api/v1/data/users"
# updated_* catches new and changed rows (API docs: use it for incremental loads).
WATERMARK = "updated_at"
LOOKBACK_DAYS = 1  # re-read the day before; Silver keeps the newest row per id
FIRST_LOAD_FROM = date(2025, 1, 1)  # before every user: the first run reads the whole table
MAX_PAGES = 200  # 122k users are 13 pages; stops a loop when has_more never ends
READ_ATTEMPTS = 3  # rows that change during a read shift the pages; read again
SCHEMA = pa.schema(
    [
        ("id", pa.int64()),
        ("first_name", pa.string()),
        ("last_name", pa.string()),
        ("email", pa.string()),
        ("age", pa.int64()),
        ("gender", pa.string()),
        ("state", pa.string()),
        ("street_address", pa.string()),
        ("postal_code", pa.string()),
        ("city", pa.string()),
        ("country", pa.string()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("traffic_source", pa.string()),
        ("created_at", pa.timestamp("us")),  # the API sends UTC without a zone
        ("updated_at", pa.timestamp("us")),
    ]
)


class SourceRowMismatch(RuntimeError):
    """Rows read differ from the count the API reports."""


def read_window(data_date: str, watermark: datetime | None) -> tuple[date, date]:
    """Days to read, both inclusive: watermark day minus lookback, up to data_date."""
    start = FIRST_LOAD_FROM if watermark is None else watermark.date() - timedelta(LOOKBACK_DAYS)
    return start, date.fromisoformat(data_date)


def fetch(start: date, end: date, cfg: config.Settings) -> tuple[list[dict], int]:
    """Every page of the window, from page 0 until has_more is false.

    Returns the rows and meta.count of the first page.
    """
    url = f"{cfg.stylehub_api_url}{ENDPOINT}"
    window = {"updated_from": start.isoformat(), "updated_to": end.isoformat()}
    rows: list[dict] = []
    expected = 0
    with api.open_session(cfg) as session:
        for page in range(MAX_PAGES):
            body = api.get_json(session, url, window | {"page": page, "page_size": api.PAGE_SIZE})
            if page == 0:
                expected = body["meta"]["count"]
            rows.extend(body["data"])
            if not body["meta"]["has_more"]:
                return rows, expected
    raise RuntimeError(f"{TABLE}: still has_more after {MAX_PAGES} pages")


def read_complete(start: date, end: date, cfg: config.Settings) -> list[dict]:
    """Rows of the window, checked against meta.count and for duplicate ids.

    Pages are cut by position (ordered by id): a user updated during the read
    leaves the window, the next pages shift and one row is skipped or read twice.
    """
    for attempt in range(1, READ_ATTEMPTS + 1):
        rows, expected = fetch(start, end, cfg)
        ids = len({row["id"] for row in rows})
        if len(rows) == ids == expected:
            return rows
        log.warning(
            "%s: read %s rows (%s ids), the API reports %s; read %s of %s",
            TABLE,
            len(rows),
            ids,
            expected,
            attempt,
            READ_ATTEMPTS,
        )
    raise SourceRowMismatch(
        f"{TABLE}: rows still differ from meta.count after {READ_ATTEMPTS} reads"
    )


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows in SCHEMA order; a missing field stops the load, a new one only warns."""
    df = pd.DataFrame(rows)
    missing = [c for c in SCHEMA.names if c not in df.columns]
    if missing:
        raise schema_check.SchemaError(f"{TABLE}: the API stopped sending {', '.join(missing)}")
    extra = sorted(set(df.columns) - set(SCHEMA.names))
    if extra:
        log.warning("%s: new API fields, not loaded: %s", TABLE, ", ".join(extra))
    df = df[SCHEMA.names].copy()
    for column in ("created_at", "updated_at"):
        df[column] = pd.to_datetime(df[column], format="ISO8601")
    return df


def ingest(data_date: str, cfg: config.Settings) -> int:
    """Write the users changed in the window to Raw as one batch; return the row count."""
    started = time.perf_counter()
    table_id = f"{cfg.project}.{cfg.bronze}.{TABLE}"
    start, end = read_window(data_date, bq.newest_before(table_id, WATERMARK, data_date, cfg))
    rows = read_complete(start, end, cfg)
    if not rows:
        log.info("%s %s: no changed users from %s", TABLE, data_date, start)
        return 0
    uri = raw_writer.write_raw(to_frame(rows), TABLE, data_date, cfg, source="api", schema=SCHEMA)
    seconds = time.perf_counter() - started
    log.info(
        "%s %s: %s rows from %s (%.1fs) -> %s", TABLE, data_date, len(rows), start, seconds, uri
    )
    return len(rows)
