"""The macro latest_bronze_snapshot, rendered with Jinja and small stand-ins for dbt's functions."""

import pytest

from stylehub.common.config import DBT_DIR

jinja2 = pytest.importorskip("jinja2")

MACRO = (DBT_DIR / "macros" / "latest_bronze_snapshot.sql").read_text(encoding="utf-8")


class Columns:
    def __init__(self, value):
        self.columns = [[value]]


class CompilerError(Exception):
    pass


def render(*, pinned=None, newest="2026-10-20", execute=True):
    """Render the macro. Returns the SQL and the list of queries it asked BigQuery."""
    asked = []

    def run_query(sql):
        asked.append(sql)
        return Columns(newest)

    def var(name, default=None):
        return {"bronze_snapshot_dates": pinned or {}}.get(name, default)

    def raise_error(message):
        raise CompilerError(message)

    env = jinja2.Environment()
    template = env.from_string(MACRO + "{{ latest_bronze_snapshot('orders') }}")
    sql = template.render(
        source=lambda schema, table: f"`p.br.{table}`",
        var=var,
        run_query=run_query,
        execute=execute,
        exceptions=type("E", (), {"raise_compiler_error": staticmethod(raise_error)}),
    )
    return " ".join(sql.split()), asked


def test_a_pinned_day_is_used_and_bigquery_is_not_asked():
    sql, asked = render(pinned={"orders": "2026-10-16"})
    assert sql == "SELECT * FROM `p.br.orders` WHERE _PARTITIONDATE = DATE '2026-10-16'"
    assert asked == []


def test_a_day_pinned_for_another_table_is_ignored():
    sql, asked = render(pinned={"users": "2026-10-16"})
    assert "DATE '2026-10-20'" in sql
    assert len(asked) == 1


def test_without_a_pinned_day_the_newest_partition_is_looked_up():
    sql, asked = render()
    assert "WHERE _PARTITIONDATE = DATE '2026-10-20'" in sql
    assert "MAX(_PARTITIONDATE)" in asked[0]


def test_a_table_without_a_partition_stops_the_compile():
    with pytest.raises(CompilerError, match="has no partition"):
        render(newest=None)


def test_while_dbt_only_parses_there_is_no_filter_and_no_query():
    sql, asked = render(execute=False)
    assert sql == "SELECT * FROM `p.br.orders`"
    assert asked == []
