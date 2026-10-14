import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from common import config
from orchestration import alerts, run_daily, runs
from orchestration.runs import run_row


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


@pytest.fixture
def fake_bigquery(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(runs, "PENDING_RUNS_FILE", tmp_path / "pending.jsonl")
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    client = MagicMock()
    monkeypatch.setattr(runs.bigquery, "Client", MagicMock(return_value=client))
    runs._runs_client.cache_clear()
    yield client
    runs._runs_client.cache_clear()


def test_record_run_creates_the_table_only_once(fake_bigquery):
    row = {"run_id": "r1"}
    assert runs.record_run(row) is True
    assert runs.record_run(row) is True
    assert fake_bigquery.query.call_count == 1  # CREATE TABLE IF NOT EXISTS ran once
    assert fake_bigquery.load_table_from_json.call_count == 2  # but both rows were saved


def test_record_run_returns_false_instead_of_raising(fake_bigquery):
    fake_bigquery.query.side_effect = RuntimeError("BigQuery is down")
    assert runs.record_run({"run_id": "r1"}) is False


def test_a_row_that_cannot_be_saved_is_kept_in_a_file(fake_bigquery):
    fake_bigquery.query.side_effect = RuntimeError("BigQuery is down")
    assert runs.record_run({"run_id": "r1"}) is False
    assert runs.read_pending() == [{"run_id": "r1"}]


def test_waiting_rows_are_sent_with_the_next_row_and_the_file_is_removed(fake_bigquery):
    runs.save_pending({"run_id": "r1"})
    assert runs.record_run({"run_id": "r2"}) is True
    sent = fake_bigquery.load_table_from_json.call_args.args[0]
    assert [r["run_id"] for r in sent] == ["r1", "r2"]
    assert runs.read_pending() == []


def test_a_damaged_pending_line_is_skipped(fake_bigquery):
    runs.PENDING_RUNS_FILE.write_text('{"run_id": "r1"}\nnot json\n', encoding="utf-8")
    assert runs.read_pending() == [{"run_id": "r1"}]
