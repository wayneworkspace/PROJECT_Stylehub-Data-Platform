"""Library functions take an optional `cfg`, so they do not need the environment."""

import pytest

from stylehub.common.bq import query_config
from stylehub.common.config import ConfigError, Settings, resolve
from stylehub.common.sql import render_sql

CFG = Settings(
    project="p1",
    bucket="b1",
    raw_prefix="raw/x",
    source="src",
    bronze="br",
    silver="sv",
    gold="gd",
    ops="op",
    location="eu",
    max_bytes_billed=123,
)


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    """Prove the point: with no settings in the environment, `settings()` would fail."""
    for name in ("GCP_PROJECT_ID", "GCS_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("stylehub.common.config.load_env", lambda: None)


def test_resolve_returns_the_given_settings_without_reading_the_environment():
    assert resolve(CFG) is CFG


def test_resolve_without_settings_reads_the_environment_and_fails_clearly():
    with pytest.raises(ConfigError, match="GCP_PROJECT_ID"):
        resolve(None)


def test_query_config_uses_the_cost_limit_of_the_given_settings():
    assert query_config(CFG).maximum_bytes_billed == 123


def test_render_sql_fills_placeholders_from_the_given_settings(tmp_path):
    sql = tmp_path / "q.sql"
    sql.write_text("SELECT 1 FROM `${project}.${bronze}.t` -- ${gold}", encoding="utf-8")
    assert render_sql(sql, CFG) == "SELECT 1 FROM `p1.br.t` -- gd"
