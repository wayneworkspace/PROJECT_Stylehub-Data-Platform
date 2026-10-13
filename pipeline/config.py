"""Cấu hình dùng chung. Đọc từ biến môi trường (xem .env.example)."""

import os
from pathlib import Path
from string import Template

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"

# Tên thư mục Raw của từng bảng, nếu khác tên bảng (theo Buổi 2: products lấy từ API).
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
    }


def render_sql(path: Path) -> str:
    """Thay ${project}, ${bronze}, ${silver}, ${gold}... trong file SQL."""
    return Template(path.read_text(encoding="utf-8")).substitute(settings())
