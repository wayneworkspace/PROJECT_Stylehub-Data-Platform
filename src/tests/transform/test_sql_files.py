import pytest

from common.config import SQL_DIR, render_sql


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")


def test_every_sql_file_renders_without_leftover_placeholders():
    paths = sorted(SQL_DIR.rglob("*.sql"))
    assert paths, "No SQL files found"
    for path in paths:
        sql = render_sql(path)
        assert "${" not in sql, path
        assert "my-project" in sql, path


def test_no_subquery_in_sql():
    for path in SQL_DIR.rglob("*.sql"):
        text = path.read_text(encoding="utf-8").upper()
        assert "(SELECT" not in text.replace("( SELECT", "(SELECT"), path
