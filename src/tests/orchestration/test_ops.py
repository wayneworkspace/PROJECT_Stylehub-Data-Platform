import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import requests
from google.api_core.exceptions import Conflict

from stylehub.ingestion.runner import IngestResult
from stylehub.orchestration import alerts, run_daily, runs
from stylehub.orchestration.runs import run_row


def test_alert_is_skipped_without_url():
    assert alerts.send_alert("hello") is False


def test_alert_is_sent_to_the_webhook(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://discord.example/webhook")
    post = MagicMock()
    monkeypatch.setattr(alerts.requests, "post", post)
    assert alerts.send_alert("x" * 5000) is True
    assert post.call_args.args == ("https://discord.example/webhook",)
    assert len(post.call_args.kwargs["json"]["content"]) == alerts.DISCORD_MAX_CHARS
    assert post.call_args.kwargs["timeout"] == alerts.REQUEST_TIMEOUT_SECONDS


def test_alert_failure_does_not_raise_or_leak_url(monkeypatch, caplog):
    secret = "https://discord.example/secret-token"
    monkeypatch.setenv("ALERT_WEBHOOK_URL", secret)

    def fail(url, **kwargs):
        raise requests.ConnectionError(f"cannot reach {url}")  # the error text holds the URL

    monkeypatch.setattr(alerts.requests, "post", fail)
    with caplog.at_level(logging.INFO):
        assert alerts.send_alert("hello") is False
    assert "secret-token" not in caplog.text


def test_alert_is_not_sent_when_the_webhook_answers_with_an_error(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://discord.example/webhook")
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("404")
    monkeypatch.setattr(alerts.requests, "post", MagicMock(return_value=response))
    assert alerts.send_alert("hello") is False


def test_run_row_has_duration():
    t1 = datetime(2026, 10, 1, 1, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 1, 1, 0, 5, tzinfo=UTC)
    row = run_row("r1", "bronze", "2026-10-01", "success", t1, t2, rows_loaded=7)
    assert row["duration_seconds"] == 5.0
    assert row["rows_loaded"] == 7 and row["error"] is None


@pytest.fixture
def spy(monkeypatch):
    calls = {"rows": [], "alerts": [], "pending": []}
    monkeypatch.setattr(run_daily, "record_run", calls["rows"].append)
    monkeypatch.setattr(run_daily, "save_pending", calls["pending"].append)
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


def test_a_step_that_exits_is_alerted(spy):
    def exits(_date):
        raise SystemExit("dbt is not installed")

    with pytest.raises(SystemExit):
        run_daily.run_step("r1", "silver", exits, "2026-10-01")
    assert len(spy["alerts"]) == 1


def test_a_step_stopped_by_ctrl_c_makes_no_network_call(spy):
    def interrupted(_date):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_daily.run_step("r1", "bronze", interrupted, "2026-10-01")
    # No BigQuery write and no alert: the shutdown must not hang. The row waits in the local file.
    assert spy["rows"] == [] and spy["alerts"] == []
    assert spy["pending"][0]["status"] == "failed"
    assert spy["pending"][0]["error"] == "interrupted: KeyboardInterrupt"


def test_alert_false_still_records_the_failure_but_sends_no_alert(spy):
    def boom(_date):
        raise RuntimeError("table not found")

    with pytest.raises(RuntimeError):
        run_daily.run_step("r1", "silver", boom, "2026-10-01", alert=False)
    assert spy["rows"][0]["status"] == "failed"
    assert spy["alerts"] == []


def test_the_no_alert_option_reaches_the_steps(monkeypatch, spy):
    seen = []
    monkeypatch.setattr(run_daily, "STEPS", [("ingest", lambda d: None)])
    monkeypatch.setattr(run_daily, "setup_logging", lambda: None)
    monkeypatch.setattr(
        run_daily, "run_step", lambda run_id, name, func, d, alert=True: seen.append(alert)
    )
    monkeypatch.setattr("sys.argv", ["x", "--date", "2026-10-01", "--no-alert"])
    run_daily.main()
    assert seen == [False]


def test_the_traceback_of_a_failed_step_is_logged(spy, caplog):
    def boom(_date):
        raise RuntimeError("table not found")

    with pytest.raises(RuntimeError):
        run_daily.run_step("r1", "silver", boom, "2026-10-01")
    failed = [r for r in caplog.records if "FAILED" in r.getMessage()]
    assert failed and failed[0].exc_info is not None


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
    monkeypatch.setattr(runs, "PENDING_RUNS_FILE", tmp_path / "pending.jsonl")
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


def test_record_run_loads_with_a_job_id(fake_bigquery):
    assert runs.record_run({"run_id": "r1"}) is True
    job_id = fake_bigquery.load_table_from_json.call_args.kwargs["job_id"]
    assert job_id.startswith("pipeline_runs_")


def test_a_retry_after_a_lost_answer_waits_for_the_first_job(fake_bigquery):
    # The first try reached BigQuery, so BigQuery refuses a second job with the same id.
    fake_bigquery.load_table_from_json.side_effect = Conflict("job exists")
    assert runs.record_run({"run_id": "r1"}) is True
    fake_bigquery.get_job.assert_called_once()
    assert runs.read_pending() == []


def test_step_ingest_adds_up_the_rows_of_all_tables(monkeypatch):
    def fake_ingest(table, data_date):
        return IngestResult(table, data_date, rows=10, mode="csv", seconds=0.1, uri="gs://x")

    monkeypatch.setattr(run_daily.csv_tables, "ingest_table", fake_ingest)
    outcome = run_daily.step_ingest("2026-10-01")
    assert outcome.rows == 10 * len(run_daily.csv_tables.CSV_TABLES)
    assert outcome.detail["rows_by_table"]["orders"] == 10


def test_a_wrong_date_stops_the_run_before_any_step(monkeypatch, spy):
    ran = []
    monkeypatch.setattr(run_daily, "STEPS", [("ingest", lambda d: ran.append(d))])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        run_daily.run_steps("2026-10-xx", "ingest", "ingest")
    assert ran == [] and spy["rows"] == []


def test_all_steps_of_one_run_share_the_run_id(monkeypatch):
    seen = []
    monkeypatch.setattr(
        run_daily, "run_step", lambda run_id, name, func, d, alert=True: seen.append(run_id)
    )
    run_daily.run_steps("2026-10-01", "ingest", "gold", run_id="scheduled__2026-10-01")
    assert seen == ["scheduled__2026-10-01"] * 4


def test_a_new_run_id_is_made_when_none_is_given(monkeypatch):
    seen = []
    monkeypatch.setattr(
        run_daily, "run_step", lambda run_id, name, func, d, alert=True: seen.append(run_id)
    )
    run_daily.run_steps("2026-10-01", "ingest", "bronze")
    assert len(set(seen)) == 1 and seen[0]


def test_the_run_id_option_reaches_the_steps(monkeypatch, spy):
    seen = []
    monkeypatch.setattr(run_daily, "STEPS", [("ingest", lambda d: None)])
    monkeypatch.setattr(run_daily, "setup_logging", lambda: None)
    monkeypatch.setattr(
        run_daily, "run_step", lambda run_id, name, func, d, alert=True: seen.append(run_id)
    )
    monkeypatch.setattr("sys.argv", ["x", "--date", "2026-10-01", "--run-id", "abc"])
    run_daily.main()
    assert seen == ["abc"]


def test_step_bronze_stops_when_a_table_has_no_raw_file(monkeypatch):
    # 0 rows is "no Raw file for this day", never a quiet success.
    monkeypatch.setattr(run_daily, "events_table_exists", lambda: True)
    monkeypatch.setattr(run_daily, "load_day", lambda table, d: 0 if table == "users" else 5)
    with pytest.raises(RuntimeError, match="bronze users: no Raw file"):
        run_daily.step_bronze("2026-10-01")


def test_step_bronze_adds_up_the_rows(monkeypatch):
    monkeypatch.setattr(run_daily, "events_table_exists", lambda: True)
    monkeypatch.setattr(run_daily, "load_day", lambda table, d: 5)
    outcome = run_daily.step_bronze("2026-10-01")
    assert outcome.rows == 5 * len(run_daily.TABLES)
    assert set(outcome.detail["rows_by_table"]) == set(run_daily.TABLES)


def test_step_bronze_tells_you_how_to_build_a_missing_events_table(monkeypatch):
    monkeypatch.setattr(run_daily, "events_table_exists", lambda: False)
    with pytest.raises(RuntimeError, match="stylehub.bronze.events_bronze"):
        run_daily.step_bronze("2026-10-01")


def test_a_row_saved_while_sending_is_not_lost(fake_bigquery):
    runs.save_pending({"run_id": "r1"})

    def late_row_arrives(rows, table, job_id):
        runs.save_pending({"run_id": "late"})  # another process fails to send at this moment
        return MagicMock()

    fake_bigquery.load_table_from_json.side_effect = late_row_arrives
    assert runs.record_run({"run_id": "r2"}) is True
    assert runs.read_pending() == [{"run_id": "late"}]  # the old code deleted this row


def test_a_failed_send_puts_every_row_back_in_one_file(fake_bigquery):
    runs.save_pending({"run_id": "r1"})
    fake_bigquery.query.side_effect = RuntimeError("BigQuery is down")
    assert runs.record_run({"run_id": "r2"}) is False
    assert [r["run_id"] for r in runs.read_pending()] == ["r1", "r2"]
    assert not list(runs.PENDING_RUNS_FILE.parent.glob("*.claimed"))


def test_a_file_that_a_dead_process_claimed_is_sent_by_the_next_run(fake_bigquery):
    dead = runs.PENDING_RUNS_FILE.with_name("pending.jsonl.dead.claimed")
    dead.write_text('{"run_id": "r0"}\n', encoding="utf-8")
    assert runs.record_run({"run_id": "r1"}) is True
    sent = fake_bigquery.load_table_from_json.call_args.args[0]
    assert [r["run_id"] for r in sent] == ["r0", "r1"]
    assert not dead.exists()


def test_the_same_rows_always_get_the_same_job_id():
    rows = [{"run_id": "r1", "step": "gold"}]
    assert runs.run_job_id(rows) == runs.run_job_id([{"step": "gold", "run_id": "r1"}])
    assert runs.run_job_id(rows) != runs.run_job_id([{"run_id": "r2", "step": "gold"}])


def test_a_step_can_return_a_detail_that_is_saved_as_json(spy):
    outcome = run_daily.StepOutcome(rows=3, detail={"rows_by_table": {"orders": 3}})
    run_daily.run_step("r1", "bronze", lambda d: outcome, "2026-10-01")
    assert spy["rows"][0]["rows_loaded"] == 3
    assert spy["rows"][0]["detail"] == '{"rows_by_table": {"orders": 3}}'


def test_a_plain_row_count_has_no_detail(spy):
    run_daily.run_step("r1", "bronze", lambda d: 5, "2026-10-01")
    assert spy["rows"][0]["rows_loaded"] == 5 and spy["rows"][0]["detail"] is None


def test_a_locked_pending_file_does_not_crash_the_step(fake_bigquery, monkeypatch):
    def locked():
        raise PermissionError("file is in use")  # for example on Windows

    monkeypatch.setattr(runs, "claim_pending", locked)
    assert runs.record_run({"run_id": "r1"}) is False
    assert runs.read_pending() == [{"run_id": "r1"}]  # the row waits for the next run
