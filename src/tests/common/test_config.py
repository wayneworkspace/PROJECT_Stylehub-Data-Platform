import dataclasses
import os

import dotenv
import pytest

from stylehub.common import config


def test_settings_use_defaults_for_optional_values():
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
    monkeypatch.setenv("BQ_GOLD", "my_gold")
    assert config.settings().gold == "my_gold"


def test_the_staging_dataset_has_a_default_and_can_be_overridden(monkeypatch):
    assert config.settings().staging == "stylehub_staging"
    monkeypatch.setenv("BQ_STAGING", "my_staging")
    assert config.settings().staging == "my_staging"


def test_settings_fail_loudly_without_project(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID")
    with pytest.raises(config.ConfigError, match="GCP_PROJECT_ID is not set"):
        config.settings()


def test_the_missing_bucket_message_says_where_to_set_it(monkeypatch):
    monkeypatch.delenv("GCS_BUCKET")
    with pytest.raises(config.ConfigError, match="secrets/.env"):
        config.settings()


def test_settings_are_read_only():
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
    monkeypatch.setattr(config, "load_dotenv", dotenv.load_dotenv)  # the real one, for this test
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("GCS_BUCKET")
    config.load_env()
    assert os.environ["GCS_BUCKET"] == "bucket-from-file"


def test_the_query_cost_limit_has_a_default_and_can_be_changed(monkeypatch):
    assert config.settings().max_bytes_billed == 50_000_000_000
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "5000")
    assert config.settings().max_bytes_billed == 5000


@pytest.mark.parametrize("value", ["abc", "0", "-1", ""])
def test_a_wrong_query_cost_limit_is_a_clear_error(monkeypatch, value):
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", value)
    with pytest.raises(config.ConfigError, match="BQ_MAX_BYTES_BILLED"):
        config.settings()
