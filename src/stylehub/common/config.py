"""Shared configuration, read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
DBT_DIR = ROOT / "dbt"
# All settings and secrets live in one file that Git ignores. Copy .env.example to this path.
ENV_FILE = ROOT / "secrets" / ".env"
# pipeline_runs rows that could not be saved to BigQuery wait here (Git ignores logs/).
PENDING_RUNS_FILE = ROOT / "logs" / "pipeline_runs_pending.jsonl"

DEFAULT_MAX_BYTES_BILLED = 50_000_000_000  # 50 GB. The biggest query (events) scans about 15 GB.


class ConfigError(RuntimeError):
    """A required setting is missing."""


def required_env(name: str) -> str:
    """The value of a required variable, or a clear message about where to set it."""
    try:
        return os.environ[name]
    except KeyError:
        raise ConfigError(
            f"{name} is not set. Copy .env.example to secrets/.env and fill it in."
        ) from None


def load_env() -> None:
    """Read secrets/.env into the environment. Variables that are already set are kept.

    A relative GOOGLE_APPLICATION_CREDENTIALS (for example secrets/key.json) is counted from the
    project folder, so the pipeline works from any folder you start it in.
    """
    load_dotenv(ENV_FILE)
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file and not Path(key_file).is_absolute():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(ROOT / key_file)


@dataclass(frozen=True)
class Settings:
    """All settings the pipeline needs. Frozen, so no step can change them by accident."""

    project: str  # GCP project id
    bucket: str  # GCS bucket of the Raw Zone (name only, no gs://)
    raw_prefix: str  # folder of the Raw Zone inside the bucket
    source: str  # dataset with the course's original tables (events, ...)
    bronze: str  # dataset names of the layers
    silver: str
    gold: str
    ops: str  # dataset of the pipeline_runs table
    location: str  # where new buckets and datasets are created
    max_bytes_billed: int = DEFAULT_MAX_BYTES_BILLED  # one query may not bill more (about 0.31 USD)
    staging: str = "stylehub_staging"  # views over Bronze that still hold personal data


def max_bytes_billed() -> int:
    """BQ_MAX_BYTES_BILLED: a query that would bill more bytes is refused by BigQuery.

    This is the safety net against one wrong query on a 108-million-row table.
    """
    value = os.environ.get("BQ_MAX_BYTES_BILLED", str(DEFAULT_MAX_BYTES_BILLED))
    try:
        limit = int(value)
    except ValueError:
        limit = 0
    if limit <= 0:
        raise ConfigError(f"BQ_MAX_BYTES_BILLED must be a whole number above 0, not {value!r}")
    return limit


def settings() -> Settings:
    """Read the settings. GCP_PROJECT_ID and GCS_BUCKET are required, the rest have defaults."""
    load_env()
    return Settings(
        project=required_env("GCP_PROJECT_ID"),
        bucket=required_env("GCS_BUCKET"),
        raw_prefix=os.environ.get("RAW_PREFIX", "raw/stylehub"),
        source=os.environ.get("BQ_SOURCE", "stylehub"),
        bronze=os.environ.get("BQ_BRONZE", "stylehub_bronze"),
        silver=os.environ.get("BQ_SILVER", "stylehub_silver"),
        gold=os.environ.get("BQ_GOLD", "stylehub_gold"),
        ops=os.environ.get("BQ_OPS", "stylehub_ops"),
        location=os.environ.get("GCP_LOCATION", "asia-southeast1"),
        max_bytes_billed=max_bytes_billed(),
        staging=os.environ.get("BQ_STAGING", "stylehub_staging"),
    )


def resolve(cfg: Settings | None) -> Settings:
    """The settings passed in, or the ones read from the environment when none were passed.

    Library functions take an optional `cfg` so a test or another caller can hand in its own
    Settings. Only the command-line entry points read the environment (via this function).
    """
    return cfg if cfg is not None else settings()


def alert_webhook_url() -> str:
    """The alert webhook URL, or "" when it is not set. It is a secret.

    It is not part of Settings, so it is never passed to dbt or filled into SQL.
    """
    return os.environ.get("ALERT_WEBHOOK_URL", "").strip()
