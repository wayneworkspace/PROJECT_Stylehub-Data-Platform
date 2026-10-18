"""Pipeline settings from environment variables, plus GCP and Postgres clients."""

import os
from pathlib import Path

import google.cloud.storage as storage
import sqlalchemy
from dotenv import load_dotenv
from google.cloud import bigquery
from pydantic import Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "include" / "sql"
DBT_DIR = ROOT / "dbt_project"
# Settings and secrets file, ignored by Git (see .env.example).
ENV_FILE = ROOT / "secrets" / ".env"


class Settings(BaseSettings):
    """All pipeline settings, read from environment variables. Read-only."""

    model_config = SettingsConfigDict(frozen=True)

    project: str = Field(validation_alias="GCP_PROJECT_ID")
    bucket: str = Field(validation_alias="GCS_BUCKET")  # Raw Zone bucket name, without gs://
    raw_prefix: str = Field("raw/stylehub", validation_alias="RAW_PREFIX")  # Raw Zone folder
    source: str = Field("stylehub", validation_alias="BQ_SOURCE")  # course source tables
    bronze: str = Field("stylehub_bronze", validation_alias="BQ_BRONZE")
    silver: str = Field("stylehub_silver", validation_alias="BQ_SILVER")
    gold: str = Field("stylehub_gold", validation_alias="BQ_GOLD")
    ops: str = Field("stylehub_ops", validation_alias="BQ_OPS")  # holds pipeline_runs
    staging: str = Field("stylehub_staging", validation_alias="BQ_STAGING")  # personal-data views
    location: str = Field("asia-southeast1", validation_alias="GCP_LOCATION")
    # Max bytes one query may bill; events scans ~15 GB.
    max_bytes_billed: PositiveInt = Field(50_000_000_000, validation_alias="BQ_MAX_BYTES_BILLED")
    # Read-only course database; SecretStr keeps the password out of logs.
    postgres_url: SecretStr | None = Field(None, validation_alias="POSTGRES_URL")


def settings() -> Settings:
    """Load secrets/.env once per command; pass the settings down as cfg."""
    load_dotenv(ENV_FILE)
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file and not Path(key_file).is_absolute():  # relative to the project folder
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(ROOT / key_file)
    return Settings()  # values come from the environment


def bq_client(cfg: Settings) -> bigquery.Client:
    return bigquery.Client(project=cfg.project)


def gcs_client(cfg: Settings) -> storage.Client:
    return storage.Client(project=cfg.project)


def pg_engine(cfg: Settings) -> sqlalchemy.Engine:
    """Postgres engine without a pool; fails clearly when POSTGRES_URL is missing."""
    if cfg.postgres_url is None:
        raise RuntimeError("POSTGRES_URL is not set in secrets/.env")
    return sqlalchemy.create_engine(
        cfg.postgres_url.get_secret_value(),
        poolclass=sqlalchemy.NullPool,
        connect_args={"connect_timeout": 30},
    )
