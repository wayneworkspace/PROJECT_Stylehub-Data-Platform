from storage import events_bronze


def test_nothing_is_built_when_the_table_exists(monkeypatch):
    calls = []
    monkeypatch.setattr(events_bronze, "events_table_exists", lambda: True)
    monkeypatch.setattr(events_bronze, "copy_events", lambda: calls.append("copy"))
    monkeypatch.setattr(events_bronze, "run_layer", lambda layer: calls.append("sql"))

    assert events_bronze.ensure_events_bronze() is False
    assert calls == []


def test_copy_then_sql_run_when_the_table_is_missing(monkeypatch):
    calls = []
    monkeypatch.setattr(events_bronze, "events_table_exists", lambda: False)
    monkeypatch.setattr(events_bronze, "copy_events", lambda: calls.append("copy") or 5)
    monkeypatch.setattr(events_bronze, "run_layer", lambda layer: calls.append(f"sql:{layer}"))

    assert events_bronze.ensure_events_bronze() is True
    assert calls == ["copy", "sql:bronze"]
