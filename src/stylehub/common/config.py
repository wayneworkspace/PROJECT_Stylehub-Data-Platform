"""Shared configuration, read from environment variables (see .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
DBT_DIR = ROOT / "dbt"
# All settings and secrets live in one file that Git ignores. Copy .env.example to this path.
ENV_FILE = ROOT / "secrets" / ".env"


def load_env() -> None:
    """Read secrets/.env into the environment. Variables that are already set are kept.

    A relative GOOGLE_APPLICATION_CREDENTIALS (for example secrets/key.json) is counted from the
    project folder, so the pipeline works from any folder you start it in.
    """
    load_dotenv(ENV_FILE)
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file and not Path(key_file).is_absolute():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(ROOT / key_file)


class Settings(BaseSettings):
    """All settings the pipeline needs, read from environment variables. Read-only."""

    model_config = SettingsConfigDict(frozen=True, populate_by_name=True)

    project: str = Field(validation_alias="GCP_PROJECT_ID")  # GCP project id
    bucket: str = Field(validation_alias="GCS_BUCKET")  # Raw Zone bucket (name only, no gs://)
    raw_prefix: str = Field("raw/stylehub", validation_alias="RAW_PREFIX")  # Raw Zone folder
    source: str = Field("stylehub", validation_alias="BQ_SOURCE")  # the course's original tables
    bronze: str = Field("stylehub_bronze", validation_alias="BQ_BRONZE")
    silver: str = Field("stylehub_silver", validation_alias="BQ_SILVER")
    gold: str = Field("stylehub_gold", validation_alias="BQ_GOLD")
    ops: str = Field("stylehub_ops", validation_alias="BQ_OPS")  # holds pipeline_runs
    staging: str = Field("stylehub_staging", validation_alias="BQ_STAGING")  # personal-data views
    location: str = Field("asia-southeast1", validation_alias="GCP_LOCATION")
    # One query may not bill more than this. The biggest one (events) scans about 15 GB.
    max_bytes_billed: PositiveInt = Field(50_000_000_000, validation_alias="BQ_MAX_BYTES_BILLED")


def settings() -> Settings:
    """Read the settings. GCP_PROJECT_ID and GCS_BUCKET are required, the rest have defaults."""
    load_env()
    return Settings()  # type: ignore[call-arg]  # the values come from the environment


def resolve(cfg: Settings | None) -> Settings:
    """The settings passed in, or the ones read from the environment when none were passed.

    Library functions take an optional `cfg` so a test or another caller can hand in its own
    Settings. Only the command-line entry points read the environment (via this function).
    """
    return cfg if cfg is not None else settings()
