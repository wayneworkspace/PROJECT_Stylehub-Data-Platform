import pytest

from stylehub.bronze import events_bronze


def fake(monkeypatch, exists, calls):
    """The table is missing before the build and there afterwards (a list of answers)."""
    answers = iter(exists)
    monkeypatch.setattr(events_bronze, "events_table_exists", lambda: next(answers))
    monkeypatch.setattr(events_bronze, "copy_events", lambda: calls.append("copy") or 5)
    monkeypatch.setattr(
        events_bronze,
        "run_layer",
        lambda layer, only_file=None: calls.append(f"sql:{layer}:{only_file}"),
    )
    monkeypatch.setattr(events_bronze, "drop_raw_copy", lambda: calls.append("drop_raw"))


def test_nothing_is_built_when_the_table_exists(monkeypatch):
    calls = []
    fake(monkeypatch, [True], calls)

    assert events_bronze.ensure_events_bronze() is False
    assert calls == []


def test_copy_then_sql_then_drop_the_copy_when_the_table_is_missing(monkeypatch):
    calls = []
    fake(monkeypatch, [False, True], calls)

    assert events_bronze.ensure_events_bronze() is True
    # Only the events SQL file runs, never every file in the folder.
    assert calls == ["copy", "sql:bronze:01_events_partitioned.sql", "drop_raw"]


def test_the_copy_is_kept_on_request(monkeypatch):
    calls = []
    fake(monkeypatch, [False, True], calls)

    events_bronze.ensure_events_bronze(keep_raw=True)
    assert "drop_raw" not in calls


def test_the_copy_is_kept_when_the_build_did_not_make_the_table(monkeypatch):
    calls = []
    fake(monkeypatch, [False, False], calls)

    with pytest.raises(RuntimeError, match="was not created"):
        events_bronze.ensure_events_bronze()
    assert "drop_raw" not in calls
