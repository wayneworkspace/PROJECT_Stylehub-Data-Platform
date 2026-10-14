import dataclasses
import os

import pytest

from pipeline import config

OPTIONAL_NAMES = (
    "GCP_LOCATION",
    "RAW_PREFIX",
    "BQ_SOURCE",
    "BQ_BRONZE",
    "BQ_SILVER",
    "BQ_GOLD",
    "BQ_OPS",
)


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
    assert cfg.location == "asia-southeast1"


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


def test_env_file_is_inside_the_secrets_folder():
    assert config.ENV_FILE == config.ROOT / "secrets" / ".env"


def test_relative_key_path_is_counted_from_the_project_folder(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "secrets/key.json")
    config.load_env()
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(config.ROOT / "secrets/key.json")


def test_absolute_key_path_is_not_changed(monkeypatch, tmp_path):
    key = str(tmp_path / "key.json")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", key)
    config.load_env()
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == key


def test_load_env_reads_the_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GCS_BUCKET=bucket-from-file\n", encoding="utf-8")
    monkeypatch.undo()  # drop the autouse patch that switches load_dotenv off
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("GCS_BUCKET", "placeholder")  # makes pytest restore the value afterwards
    monkeypatch.delenv("GCS_BUCKET")
    config.load_env()
    assert os.environ["GCS_BUCKET"] == "bucket-from-file"
