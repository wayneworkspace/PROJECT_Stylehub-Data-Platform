"""Shared configuration, read from environment variables (see .env.example)."""

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"

# Raw folder name per table when it differs from the table name
# (session 2: products come from the API).
RAW_DIR = {"products": "products_api"}


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


def settings() -> Settings:
    """Read the settings. GCP_PROJECT_ID and GCS_BUCKET are required, the rest have defaults."""
    load_dotenv(ROOT / ".env")
    return Settings(
        project=os.environ["GCP_PROJECT_ID"],
        bucket=os.environ["GCS_BUCKET"],
        raw_prefix=os.environ.get("RAW_PREFIX", "raw/stylehub"),
        source=os.environ.get("BQ_SOURCE", "stylehub"),
        bronze=os.environ.get("BQ_BRONZE", "stylehub_bronze"),
        silver=os.environ.get("BQ_SILVER", "stylehub_silver"),
        gold=os.environ.get("BQ_GOLD", "stylehub_gold"),
        ops=os.environ.get("BQ_OPS", "stylehub_ops"),
    )


def render_sql(path: Path) -> str:
    """Substitute ${project}, ${bronze}, ${silver}, ${gold}, ... in a SQL file."""
    return Template(path.read_text(encoding="utf-8")).substitute(asdict(settings()))
