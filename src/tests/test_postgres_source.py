import pytest

from sources import postgres


@pytest.fixture
def connect_args(monkeypatch):
    """Replace psycopg2.connect and remember the arguments it received."""
    received = {}
    monkeypatch.setattr(postgres.psycopg2, "connect", lambda **kwargs: received.update(kwargs))
    for name, value in {
        "PG_HOST": "db.example.test",
        "PG_DATABASE": "stylehub",
        "PG_USER": "student_readonly",
        "PG_PASSWORD": "not-a-real-password",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("PG_PORT", raising=False)
    monkeypatch.delenv("PG_SSLMODE", raising=False)
    return received


def test_connect_uses_the_settings_and_safe_defaults(connect_args):
    postgres.connect()
    assert connect_args["host"] == "db.example.test"
    assert connect_args["port"] == "5432"
    assert connect_args["dbname"] == "stylehub"
    assert connect_args["sslmode"] == "prefer"


def test_connect_can_require_tls(connect_args, monkeypatch):
    monkeypatch.setenv("PG_SSLMODE", "require")
    postgres.connect()
    assert connect_args["sslmode"] == "require"


def test_connect_fails_loudly_without_a_host(connect_args, monkeypatch):
    monkeypatch.delenv("PG_HOST")
    with pytest.raises(KeyError):
        postgres.connect()
