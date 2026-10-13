from datetime import date

import pytest

from ingestion.incremental import window_for
from pipeline.config import SQL_DIR, render_sql


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")


def test_window_covers_lookback_and_whole_day():
    start, end = window_for(date(2026, 10, 5), lookback_days=1)
    assert start.isoformat() == "2026-10-04T00:00:00"
    assert end.isoformat() == "2026-10-06T00:00:00"


def test_every_sql_file_renders_without_leftover_placeholders():
    paths = sorted(SQL_DIR.rglob("*.sql"))
    assert paths, "Không thấy file SQL nào"
    for path in paths:
        sql = render_sql(path)
        assert "${" not in sql, path
        assert "my-project" in sql, path


def test_sql_files_are_ordered_by_numeric_prefix():
    for layer in ("silver", "gold", "checks"):
        names = [p.name for p in sorted((SQL_DIR / layer).glob("*.sql"))]
        assert all(name[:2].isdigit() for name in names), layer


def test_no_subquery_in_sql():
    for path in SQL_DIR.rglob("*.sql"):
        text = path.read_text(encoding="utf-8").upper()
        assert "(SELECT" not in text.replace("( SELECT", "(SELECT"), path
