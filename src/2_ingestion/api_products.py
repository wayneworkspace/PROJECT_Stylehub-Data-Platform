"""Full snapshot of the StyleHub API products into the Raw Zone, once a day."""

import time
from decimal import Decimal
from importlib import import_module

import pandas as pd
import pyarrow as pa

get_logger = import_module("src.0_utils.logger").get_logger

api = import_module("src.1_source.api")
config = import_module("src.1_source.config")
raw_writer = import_module("src.2_ingestion.raw_writer")
schema_check = import_module("src.2_ingestion.schema_check")

log = get_logger(__name__)

TABLE = "api_products"
ENDPOINT = "stylehub-products"
# The API needs a date filter; a date before every product reads the whole table.
# Dates do not split this table (most rows share one updated_at), so it is a full load.
FULL_LOAD_FROM = "2025-01-01"
MAX_PAGES = 200  # 29k products are 30 pages; stops a loop when has_more never ends
# Same columns as Postgres products: the API serves the same table.
SCHEMA = pa.schema(
    [
        ("id", pa.int64()),
        ("cost", pa.decimal128(38, 9)),
        ("category", pa.string()),
        ("name", pa.string()),
        ("brand", pa.string()),
        ("retail_price", pa.decimal128(38, 9)),
        ("department", pa.string()),
        ("sku", pa.string()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("updated_at", pa.timestamp("us", tz="UTC")),
    ]
)


class SourceRowMismatch(RuntimeError):
    """Rows read differ from the count the API reports."""


def fetch_all(cfg: config.Settings) -> tuple[list[dict], int]:
    """Every page, from page 0 until has_more is false; return rows and meta.count."""
    url = f"{api.base_url(cfg)}/{ENDPOINT}"
    rows: list[dict] = []
    with api.open_session(cfg) as session:
        for page in range(MAX_PAGES):
            params = {"updated_from": FULL_LOAD_FROM, "page": page, "page_size": api.PAGE_SIZE}
            body = api.get_json(session, url, params)
            rows.extend(body["data"])
            if not body["meta"]["has_more"]:
                return rows, body["meta"]["count"]
    raise RuntimeError(f"{TABLE}: still has_more after {MAX_PAGES} pages")


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows in SCHEMA order; a missing column stops the load, a new one only warns."""
    df = pd.DataFrame(rows)
    missing = [c for c in SCHEMA.names if c not in df.columns]
    if missing:
        raise schema_check.SchemaError(f"{TABLE}: the API stopped sending {', '.join(missing)}")
    extra = sorted(set(df.columns) - set(SCHEMA.names))
    if extra:
        log.warning("%s: new API fields, not loaded: %s", TABLE, ", ".join(extra))
    df = df[SCHEMA.names].copy()
    for column in ("created_at", "updated_at"):
        df[column] = pd.to_datetime(df[column], utc=True, format="ISO8601")
    # Decimal through text, so 0.1 stays 0.1 and never becomes 0.1000000000000000055.
    for column in ("cost", "retail_price"):
        df[column] = df[column].map(lambda v: None if pd.isna(v) else Decimal(str(v)))
    return df


def ingest(data_date: str, cfg: config.Settings) -> int:
    """Write today's full products snapshot to Raw; return its row count.

    Rows are checked against meta.count and for duplicate ids: a product
    added while paging shifts the pages, so one is read twice or missed.
    """
    started = time.perf_counter()
    rows, expected = fetch_all(cfg)
    df = to_frame(rows)
    if len(df) != expected or df["id"].nunique() != len(df):
        raise SourceRowMismatch(
            f"{TABLE}: read {len(df)} rows ({df['id'].nunique()} ids), the API reports {expected}"
        )
    uri = raw_writer.write_raw(df, TABLE, data_date, cfg, source="api", schema=SCHEMA)
    log.info(
        "%s %s: %s rows (%.1fs) -> %s",
        TABLE,
        data_date,
        len(df),
        time.perf_counter() - started,
        uri,
    )
    return len(df)
