"""One place that creates the Google Cloud clients (BigQuery and Cloud Storage)."""

import google.cloud.storage as storage  # this form, because mypy finds no type hints for storage
from google.cloud import bigquery

from stylehub.common.config import Settings


def bq_client(cfg: Settings) -> bigquery.Client:
    return bigquery.Client(project=cfg.project)


def gcs_client(cfg: Settings) -> storage.Client:
    return storage.Client(project=cfg.project)
