"""Create the GCS bucket and the BigQuery datasets. Run once by hand.

Safe to run again: anything that already exists is left alone. Everything is created in
GCP_LOCATION, so loads between the bucket and the datasets work.

Usage: python -m stylehub.setup.setup_gcp [--dry-run]
"""

import argparse
import logging

import google.cloud.storage as storage
from google.cloud import bigquery

from stylehub.common.clients import bq_client, gcs_client
from stylehub.common.config import SQL_DIR, Settings, settings
from stylehub.common.logs import setup_cli_logging
from stylehub.common.sql import render_sql

log = logging.getLogger(__name__)


def dataset_ids(cfg: Settings) -> list[str]:
    """Course source dataset first, then the layers (staging holds personal data) and ops."""
    return [cfg.source, cfg.bronze, cfg.staging, cfg.silver, cfg.gold, cfg.ops]


def ensure_bucket(client: storage.Client, name: str, location: str) -> bool:
    """Create the bucket if it is missing. Return True if it was created."""
    if client.lookup_bucket(name) is not None:
        return False
    bucket = client.bucket(name)
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True  # no per-file ACLs
    # Raw is the copy that Bronze can be rebuilt from, and there is no other backup. With versioning
    # on, a file that is overwritten or deleted by mistake can be brought back.
    bucket.versioning_enabled = True
    client.create_bucket(bucket, location=location)
    return True


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    """Create the dataset if it is missing. An existing dataset is left alone."""
    dataset = bigquery.Dataset(f"{client.project}.{dataset_id}")
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)


def ensure_ops_tables(client: bigquery.Client) -> list[str]:
    """Create the pipeline_runs table and apply its migrations (src/stylehub/sql/ops/).

    This is set-up work, so it runs here once. The daily pipeline does not change the table.
    Return the names of the SQL files that ran.
    """
    names = []
    for path in sorted((SQL_DIR / "ops").glob("*.sql")):
        client.query(render_sql(path)).result()
        names.append(path.name)
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only print what would be created")
    args = parser.parse_args()
    setup_cli_logging()
    cfg = settings()

    if args.dry_run:
        log.info(f"Would make sure this exists in {cfg.location} (project {cfg.project}):")
        log.info(f"  bucket   gs://{cfg.bucket}")
        for dataset_id in dataset_ids(cfg):
            log.info(f"  dataset  {dataset_id}")
        log.info("  table    pipeline_runs (src/stylehub/sql/ops/)")
        return

    storage_client = gcs_client(cfg)
    created = ensure_bucket(storage_client, cfg.bucket, cfg.location)
    log.info(f"bucket   gs://{cfg.bucket}: {'created' if created else 'already exists'}")

    bigquery_client = bq_client(cfg)
    for dataset_id in dataset_ids(cfg):
        ensure_dataset(bigquery_client, dataset_id, cfg.location)
        log.info(f"dataset  {dataset_id}: ready")
    for name in ensure_ops_tables(bigquery_client):
        log.info(f"ops      {name}: done")


if __name__ == "__main__":
    main()
