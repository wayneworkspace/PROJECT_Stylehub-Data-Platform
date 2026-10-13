"""Shared configuration, read from environment variables (see .env.example)."""

import os
from pathlib import Path
from string import Template

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"

# Raw folder name per table when it differs from the table name
# (session 2: products come from the API).
RAW_DIR = {"products": "products_api"}


def settings() -> dict[str, str]:
    load_dotenv(ROOT / ".env")
    return {
        "project": os.environ["GCP_PROJECT_ID"],
        "bucket": os.environ["GCS_BUCKET"],
        "raw_prefix": os.environ.get("RAW_PREFIX", "raw/stylehub"),
        "source": os.environ.get("BQ_SOURCE", "stylehub"),
        "bronze": os.environ.get("BQ_BRONZE", "stylehub_bronze"),
        "silver": os.environ.get("BQ_SILVER", "stylehub_silver"),
        "gold": os.environ.get("BQ_GOLD", "stylehub_gold"),
        "ops": os.environ.get("BQ_OPS", "stylehub_ops"),
    }


def render_sql(path: Path) -> str:
    """Substitute ${project}, ${bronze}, ${silver}, ${gold}, ... in a SQL file."""
    return Template(path.read_text(encoding="utf-8")).substitute(settings())
