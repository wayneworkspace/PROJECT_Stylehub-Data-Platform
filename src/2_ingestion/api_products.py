"""Products API into the Raw Zone: one Parquet part per page, one batch per run."""

import time
from importlib import import_module

import pandas as pd
import requests

get_logger = import_module("src.0_utils.logger").get_logger
api = import_module("src.1_source.api")
config = import_module("src.1_source.config")
raw_writer = import_module("src.2_ingestion.raw_writer")
schema_check = import_module("src.2_ingestion.schema_check")

log = get_logger(__name__)

TABLE = "api_products"
# API key -> column and fixed dtype, so every page has one Parquet schema.
COLUMNS = {
    "id": ("id", "Int64"),
    "title": ("title", "string"),
    "category": ("category", "string"),
    "brand": ("brand", "string"),
    "price": ("price", "float64"),
    "discountPercentage": ("discount_percentage", "float64"),
    "rating": ("rating", "float64"),
    "stock": ("stock", "Int64"),
    "availabilityStatus": ("availability_status", "string"),
}
OPTIONAL_KEYS = {"brand"}  # the API leaves brand out for some products


def to_frame(products: list[dict]) -> pd.DataFrame:
    """Flat, typed rows; fails when a required key is missing."""
    required = set(COLUMNS) - OPTIONAL_KEYS | {"meta"}
    missing = sorted({k for p in products for k in required if k not in p})
    if missing:
        raise schema_check.SchemaError(f"{TABLE}: the API stopped sending: {', '.join(missing)}")
    rows = [
        {col: p.get(key) for key, (col, _) in COLUMNS.items()}
        | {"updated_at": p["meta"].get("updatedAt")}
        for p in products
    ]
    df = pd.DataFrame(rows, columns=[col for col, _ in COLUMNS.values()] + ["updated_at"])
    df = df.astype(dict(COLUMNS.values()))
    df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True)
    return df


def ingest_page(page: dict, data_date: str) -> int:
    """Fetch one page and write it as one part of the run's batch; return rows."""
    cfg = config.settings()
    started = time.perf_counter()
    with requests.Session() as session:
        body = api.get_page(session, page["base_url"], page["skip"], page["limit"])
    df = to_frame(body["products"])
    if df.empty:
        log.info("%s skip=%s: empty page", TABLE, page["skip"])
        return 0
    part = f"part_{page['skip']:06d}"  # same name on a retry, so the file is replaced
    uri = raw_writer.write_raw(
        df, TABLE, data_date, cfg, source="api", batch_id=page["batch_id"], part=part
    )
    log.info(
        "%s skip=%s: %s rows (%.1fs) -> %s",
        TABLE,
        page["skip"],
        len(df),
        time.perf_counter() - started,
        uri,
    )
    return len(df)
