"""Fixtures that every test gets without asking."""

import pytest

from stylehub.common import config

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
def gcp_env(monkeypatch):
    """The same settings on every computer, and nothing from your real secrets/.env.

    A test that needs another value sets it after this fixture runs.
    """
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name in OPTIONAL_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)  # a test must never send a real alert
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
