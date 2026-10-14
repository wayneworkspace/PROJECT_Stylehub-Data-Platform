import dataclasses

import pytest

from pipeline import config

OPTIONAL_NAMES = ("RAW_PREFIX", "BQ_SOURCE", "BQ_BRONZE", "BQ_SILVER", "BQ_GOLD", "BQ_OPS")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Do not read the real .env file, so the tests give the same result on every computer.
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name in OPTIONAL_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_settings_use_defaults_for_optional_values(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    cfg = config.settings()
    assert (cfg.project, cfg.bucket) == ("my-project", "my-bucket")
    assert (cfg.bronze, cfg.silver, cfg.gold) == (
        "stylehub_bronze",
        "stylehub_silver",
        "stylehub_gold",
    )
    assert cfg.raw_prefix == "raw/stylehub"


def test_settings_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    monkeypatch.setenv("BQ_GOLD", "my_gold")
    assert config.settings().gold == "my_gold"


def test_settings_fail_loudly_without_project(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    with pytest.raises(KeyError):
        config.settings()


def test_settings_are_read_only(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.settings().project = "other"
