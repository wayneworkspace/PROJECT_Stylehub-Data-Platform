"""The "did not run" check: stale means no good run, or one that is too old."""

from datetime import UTC, datetime, timedelta

from orchestration import check_freshness
from orchestration.check_freshness import is_stale

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=UTC)


def test_recent_run_is_fresh():
    assert not is_stale(NOW - timedelta(hours=5), NOW, 26)


def test_old_run_is_stale():
    assert is_stale(NOW - timedelta(hours=30), NOW, 26)


def test_no_run_is_stale():
    assert is_stale(None, NOW, 26)


def test_main_alerts_and_returns_1_when_stale(monkeypatch):
    sent = []
    monkeypatch.setattr(check_freshness, "last_success", lambda: None)
    monkeypatch.setattr(check_freshness, "send_alert", sent.append)
    monkeypatch.setattr("sys.argv", ["x"])
    assert check_freshness.main() == 1
    assert "DID NOT RUN" in sent[0]


def test_main_is_quiet_when_fresh(monkeypatch):
    sent = []
    monkeypatch.setattr(check_freshness, "last_success", lambda: datetime.now(UTC))
    monkeypatch.setattr(check_freshness, "send_alert", sent.append)
    monkeypatch.setattr("sys.argv", ["x"])
    assert check_freshness.main() == 0
    assert sent == []
