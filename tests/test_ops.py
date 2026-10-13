import logging
from datetime import UTC, datetime

import pytest

from pipeline import alerts, run_daily
from pipeline.runs import run_row


def test_alert_is_skipped_without_url(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert alerts.send_alert("hello") is False


def test_alert_failure_does_not_raise_or_leak_url(monkeypatch, caplog):
    secret = "http://127.0.0.1:1/secret-token"
    monkeypatch.setenv("ALERT_WEBHOOK_URL", secret)
    with caplog.at_level(logging.INFO):
        assert alerts.send_alert("hello") is False
    assert "secret-token" not in caplog.text


def test_run_row_has_duration():
    t1 = datetime(2026, 10, 1, 1, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 1, 1, 0, 5, tzinfo=UTC)
    row = run_row("r1", "bronze", "2026-10-01", "success", t1, t2, rows_loaded=7)
    assert row["duration_seconds"] == 5.0
    assert row["rows_loaded"] == 7 and row["error"] is None


@pytest.fixture
def spy(monkeypatch):
    calls = {"rows": [], "alerts": []}
    monkeypatch.setattr(run_daily, "record_run", calls["rows"].append)
    monkeypatch.setattr(run_daily, "send_alert", calls["alerts"].append)
    return calls


def test_successful_step_is_recorded_without_alert(spy):
    run_daily.run_step("r1", "bronze", lambda d: 42, "2026-10-01")
    assert spy["rows"][0]["status"] == "success"
    assert spy["rows"][0]["rows_loaded"] == 42
    assert spy["alerts"] == []


def test_failed_step_is_recorded_alerted_and_raised(spy):
    def boom(_date):
        raise RuntimeError("table not found")

    with pytest.raises(RuntimeError):
        run_daily.run_step("r1", "silver", boom, "2026-10-01")
    assert spy["rows"][0]["status"] == "failed"
    assert "table not found" in spy["rows"][0]["error"]
    assert "silver" in spy["alerts"][0] and "2026-10-01" in spy["alerts"][0]


def test_failed_check_exits_and_alerts(spy):
    def checks(_date):
        raise SystemExit("Data checks failed")

    with pytest.raises(SystemExit):
        run_daily.run_step("r1", "checks", checks, "2026-10-01")
    assert len(spy["alerts"]) == 1


def test_to_step_stops_early(monkeypatch, spy):
    ran = []
    names = ("ingest", "bronze", "silver")
    monkeypatch.setattr(run_daily, "STEPS", [(n, lambda d, n=n: ran.append(n)) for n in names])
    monkeypatch.setattr(run_daily, "setup_logging", lambda: None)
    # argparse choices come from STEPS, so the patched names are valid
    monkeypatch.setattr("sys.argv", ["x", "--date", "2026-10-01", "--to-step", "bronze"])
    run_daily.main()
    assert ran == ["ingest", "bronze"]
