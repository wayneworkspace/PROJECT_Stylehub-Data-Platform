"""Upload local CSV files to the bucket and load them into BigQuery (session 1, exercise 1).

For each file:
  1. copy it to gs://<bucket>/landing/stylehub/<file>.csv (skipped if the same file is there),
  2. load it into <source dataset>.<file name without .csv> (an existing table is replaced),
  3. print the file size and the table size, to answer the exercise question:
     "why does BigQuery process a different number of bytes than the file size?"

BigQuery detects the column types from the file. Check the schema before you rely on it.
Big files (events.csv is about 16 GB) take a long time to upload. Run them on purpose.

Usage:
    python -m pipeline.load_csv                       # every .csv in data/raw_data
    python -m pipeline.load_csv --file data/raw_data/orders.csv --file data/raw_data/users.csv
    python -m pipeline.load_csv --dir some/other/folder
"""

import argparse
from pathlib import Path

from google.cloud import bigquery, storage

from pipeline.config import ROOT, settings

DEFAULT_CSV_DIR = ROOT / "data" / "raw_data"
LANDING_PREFIX = "landing/stylehub"  # copies of the CSV files. This is not the Raw Zone.
UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024  # upload big files in pieces, so a failure restarts one piece


def table_name_for(path: Path) -> str:
    """orders.csv -> orders"""
    return path.stem


def find_csv_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise SystemExit(f"No .csv files in {directory}")
    return files


def format_size(n_bytes: int) -> str:
    size = float(n_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def upload_csv(bucket: storage.Bucket, local_file: Path, blob_path: str) -> str:
    """Copy the file to the bucket and return its gs:// address."""
    existing = bucket.get_blob(blob_path)
    if existing is not None and existing.size == local_file.stat().st_size:
        print("  already in the bucket (same size), upload skipped")
    else:
        blob = bucket.blob(blob_path)
        blob.chunk_size = UPLOAD_CHUNK_BYTES
        blob.upload_from_filename(str(local_file))
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


def load_files(files: list[Path]) -> None:
    cfg = settings()
    bucket = storage.Client(project=cfg.project).bucket(cfg.bucket)
    client = bigquery.Client(project=cfg.project)
    for path in files:
        print(f"{path.name} ({format_size(path.stat().st_size)})")
        uri = upload_csv(bucket, path, f"{LANDING_PREFIX}/{path.name}")
        table_id = f"{cfg.project}.{cfg.source}.{table_name_for(path)}"
        table = load_csv_into_bigquery(client, uri, table_id)
        print(f"  -> {table_id}: {table.num_rows:,} rows, {format_size(table.num_bytes)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--file", action="append", type=Path, help="one CSV file (repeat the flag)")
    where.add_argument("--dir", type=Path, default=DEFAULT_CSV_DIR, help="a folder of CSV files")
    args = parser.parse_args()
    files = args.file or find_csv_files(args.dir)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise SystemExit(f"File not found: {', '.join(missing)}")
    load_files(files)


if __name__ == "__main__":
    main()
