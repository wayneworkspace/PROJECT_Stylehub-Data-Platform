"""The "did not run" check: stale means no good run, or one that is too old."""

from datetime import UTC, datetime, timedelta

from stylehub.orchestration import check_freshness
from stylehub.orchestration.check_freshness import is_stale

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


def fake_client(monkeypatch, rows_by_query):
    """A BigQuery client whose answer depends on a word in the query."""
    monkeypatch.setattr(check_freshness.bigquery, "Client", lambda project: object())

    def run_query(client, query):
        for word, rows in rows_by_query.items():
            if word in query:
                if isinstance(rows, Exception):
                    raise rows
                return rows
        raise AssertionError(query)

    monkeypatch.setattr(check_freshness, "run_query", run_query)


def row(**fields):
    return type("Row", (), fields)()


def test_the_complete_run_needs_all_four_steps(monkeypatch):
    seen = []
    monkeypatch.setattr(check_freshness.bigquery, "Client", lambda project: object())
    monkeypatch.setattr(
        check_freshness, "run_query", lambda c, q: seen.append(q) or [row(last_finished=NOW)]
    )
    assert check_freshness.last_complete_run() == NOW
    assert "n_steps = 4" in seen[0] and "GROUP BY data_date" in seen[0]
    assert "'ingest'" in seen[0] and "'gold'" in seen[0]


def test_a_missing_runs_table_means_no_complete_run(monkeypatch):
    from google.api_core.exceptions import NotFound

    fake_client(monkeypatch, {"pipeline_runs": NotFound("no table")})
    assert check_freshness.last_complete_run() is None


def test_bronze_load_is_the_oldest_of_the_tables(monkeypatch):
    days = iter([NOW, NOW - timedelta(hours=40), NOW - timedelta(hours=3), NOW])
    monkeypatch.setattr(check_freshness.bigquery, "Client", lambda project: object())
    monkeypatch.setattr(check_freshness, "run_query", lambda c, q: [row(d=next(days))])
    assert check_freshness.last_bronze_load() == NOW - timedelta(hours=40)


def test_an_empty_bronze_table_means_nothing_to_trust(monkeypatch):
    fake_client(monkeypatch, {"stylehub_bronze": [row(d=None)]})
    assert check_freshness.last_bronze_load() is None


def test_a_green_gold_run_does_not_hide_old_data(monkeypatch):
    old = NOW - timedelta(hours=40)
    monkeypatch.setattr(check_freshness, "last_complete_run", lambda: NOW)
    monkeypatch.setattr(check_freshness, "last_bronze_load", lambda: old)
    assert check_freshness.last_success() == old


class FakeBigQuery:
    """A BigQuery client passed in directly: no monkeypatching of bigquery.Client."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        return self

    def result(self):
        return self.rows


def test_a_client_can_be_passed_in_to_the_run_check():
    client = FakeBigQuery([row(last_finished=NOW)])
    assert check_freshness.last_complete_run(client) == NOW
    assert "pipeline_runs" in client.queries[0]


def test_a_client_can_be_passed_in_to_the_bronze_check():
    older = NOW - timedelta(hours=3)
    client = FakeBigQuery([row(d=older)])
    assert check_freshness.last_bronze_load(client) == older
    assert len(client.queries) == len(check_freshness.BRONZE_TABLES)
