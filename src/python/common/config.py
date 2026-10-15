"""Shared configuration, read from environment variables (see .env.example)."""

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
SQL_DIR = ROOT / "src" / "sql"
DBT_DIR = ROOT / "dbt"
# All settings and secrets live in one file that Git ignores. Copy .env.example to this path.
ENV_FILE = ROOT / "secrets" / ".env"
# pipeline_runs rows that could not be saved to BigQuery wait here (Git ignores logs/).
PENDING_RUNS_FILE = ROOT / "logs" / "pipeline_runs_pending.jsonl"

# Raw folder name per table when it differs from the table name (none for now).
RAW_DIR: dict[str, str] = {}


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


def settings() -> Settings:
    """Read the settings. GCP_PROJECT_ID and GCS_BUCKET are required, the rest have defaults."""
    load_env()
    return Settings(
        project=os.environ["GCP_PROJECT_ID"],
        bucket=os.environ["GCS_BUCKET"],
        raw_prefix=os.environ.get("RAW_PREFIX", "raw/stylehub"),
        source=os.environ.get("BQ_SOURCE", "stylehub"),
        bronze=os.environ.get("BQ_BRONZE", "stylehub_bronze"),
        silver=os.environ.get("BQ_SILVER", "stylehub_silver"),
        gold=os.environ.get("BQ_GOLD", "stylehub_gold"),
        ops=os.environ.get("BQ_OPS", "stylehub_ops"),
        location=os.environ.get("GCP_LOCATION", "asia-southeast1"),
    )


def alert_webhook_url() -> str:
    """The alert webhook URL, or "" when it is not set. It is a secret.

    It is not part of Settings, so it is never passed to dbt or filled into SQL.
    """
    return os.environ.get("ALERT_WEBHOOK_URL", "").strip()


def render_sql(path: Path) -> str:
    """Substitute ${project}, ${bronze}, ${silver}, ${gold}, ... in a SQL file."""
    return Template(path.read_text(encoding="utf-8")).substitute(asdict(settings()))
