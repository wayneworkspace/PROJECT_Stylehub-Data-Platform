"""Create the GCS bucket and the BigQuery datasets (session 1, exercise 1).

Safe to run again: anything that already exists is left alone. New ones are created in
GCP_LOCATION. The bucket and the datasets should share one location, or loads between them fail.

Usage: python -m storage.setup_gcp [--dry-run]
"""

import argparse

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage

from common.config import Settings, settings


def dataset_ids(cfg: Settings) -> list[str]:
    """Course source dataset first, then the layers and the ops dataset."""
    return [cfg.source, cfg.bronze, cfg.silver, cfg.gold, cfg.ops]


def ensure_bucket(client: storage.Client, name: str, location: str) -> bool:
    """Create the bucket if it is missing. Return True if it was created."""
    if client.lookup_bucket(name) is not None:
        return False
    bucket = client.bucket(name)
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True  # no per-file ACLs
    client.create_bucket(bucket, location=location)
    return True


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> bool:
    """Create the dataset if it is missing. Return True if it was created."""
    try:
        client.get_dataset(dataset_id)
        return False
    except NotFound:
        pass
    dataset = bigquery.Dataset(f"{client.project}.{dataset_id}")
    dataset.location = location
    client.create_dataset(dataset)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only print what would be created")
    args = parser.parse_args()
    cfg = settings()

    if args.dry_run:
        print(f"Would make sure this exists in {cfg.location} (project {cfg.project}):")
        print(f"  bucket   gs://{cfg.bucket}")
        for dataset_id in dataset_ids(cfg):
            print(f"  dataset  {dataset_id}")
        return

    storage_client = storage.Client(project=cfg.project)
    created = ensure_bucket(storage_client, cfg.bucket, cfg.location)
    print(f"bucket   gs://{cfg.bucket}: {'created' if created else 'already exists'}")

    bigquery_client = bigquery.Client(project=cfg.project)
    for dataset_id in dataset_ids(cfg):
        created = ensure_dataset(bigquery_client, dataset_id, cfg.location)
        print(f"dataset  {dataset_id}: {'created' if created else 'already exists'}")


if __name__ == "__main__":
    main()
