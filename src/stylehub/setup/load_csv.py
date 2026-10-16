"""Upload local CSV files to the bucket and load them into BigQuery. Run once by hand.

Each file is copied to gs://<bucket>/landing/stylehub/ and loaded into <source dataset>.<name>.
BigQuery detects the column types from the file: check the schema before you rely on it.
events.csv is about 16 GB, so upload it on purpose.

Usage:
    python -m stylehub.setup.load_csv                       # every .csv in data/raw_data
    python -m stylehub.setup.load_csv --file data/raw_data/orders.csv
"""

import argparse
import logging
from pathlib import Path

import google.cloud.storage as storage
from google.cloud import bigquery

from stylehub.common.clients import bq_client, gcs_client
from stylehub.common.config import ROOT, Settings, resolve
from stylehub.common.logs import setup_cli_logging

log = logging.getLogger(__name__)

DEFAULT_CSV_DIR = ROOT / "data" / "raw_data"
LANDING_PREFIX = "landing/stylehub"  # copies of the CSV files. This is not the Raw Zone.


def find_csv_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise SystemExit(f"No .csv files in {directory}")
    return files


def upload_csv(bucket: storage.Bucket, local_file: Path, blob_path: str) -> str:
    """Copy the file to the bucket and return its gs:// address."""
    bucket.blob(blob_path).upload_from_filename(str(local_file))
    return f"gs://{bucket.name}/{blob_path}"


def load_csv_into_bigquery(client: bigquery.Client, uri: str, table_id: str) -> bigquery.Table:
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,  # the header line
        autodetect=True,
        allow_quoted_newlines=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.load_table_from_uri(uri, table_id, job_config=job_config).result()
    return client.get_table(table_id)


def load_files(files: list[Path], cfg: Settings | None = None) -> None:
    cfg = resolve(cfg)
    bucket = gcs_client(cfg).bucket(cfg.bucket)
    client = bq_client(cfg)
    for path in files:
        log.info(f"{path.name} ({path.stat().st_size / 1e6:,.1f} MB)")
        uri = upload_csv(bucket, path, f"{LANDING_PREFIX}/{path.name}")
        table_id = f"{cfg.project}.{cfg.source}.{path.stem}"
        table = load_csv_into_bigquery(client, uri, table_id)
        log.info(f"  -> {table_id}: {table.num_rows:,} rows, {table.num_bytes / 1e6:,.1f} MB")


def main() -> None:
    parser = argparse.ArgumentParser()
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--file", action="append", type=Path, help="one CSV file (repeat the flag)")
    where.add_argument("--dir", type=Path, default=DEFAULT_CSV_DIR, help="a folder of CSV files")
    args = parser.parse_args()
    setup_cli_logging()
    files = args.file or find_csv_files(args.dir)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise SystemExit(f"File not found: {', '.join(missing)}")
    load_files(files)


if __name__ == "__main__":
    main()
