"""One-time setup: upload data/raw_data CSVs, load them into BigQuery."""

from importlib import import_module
from pathlib import Path

import google.cloud.storage as storage
from google.cloud import bigquery

get_logger = import_module("src.0_utils.logger").get_logger

config = import_module("src.1_source.config")

log = get_logger(__name__)

DEFAULT_CSV_DIR = config.ROOT / "data" / "raw_data"
LANDING_PREFIX = "landing/stylehub"  # copies of the CSV files, not the Raw Zone


def find_csv_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise SystemExit(f"No .csv files in {directory}")
    return files


def upload_csv(bucket: storage.Bucket, local_file: Path, blob_path: str) -> str:
    """Copy the file to the bucket; return its gs:// URI."""
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


def load_files(files: list[Path], cfg: config.Settings) -> None:
    bucket = config.gcs_client(cfg).bucket(cfg.bucket)
    client = config.bq_client(cfg)
    for path in files:
        log.info(f"{path.name} ({path.stat().st_size / 1e6:,.1f} MB)")
        uri = upload_csv(bucket, path, f"{LANDING_PREFIX}/{path.name}")
        table_id = f"{cfg.project}.{cfg.source}.{path.stem}"
        table = load_csv_into_bigquery(client, uri, table_id)
        log.info(f"  -> {table_id}: {table.num_rows:,} rows, {table.num_bytes / 1e6:,.1f} MB")


def main() -> None:
    load_files(find_csv_files(DEFAULT_CSV_DIR), config.settings())


if __name__ == "__main__":
    main()
