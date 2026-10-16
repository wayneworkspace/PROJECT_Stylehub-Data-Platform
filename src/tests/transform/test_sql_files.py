import re

import pytest

from stylehub.common.config import SQL_DIR
from stylehub.common.sql import render_sql

SQL_FILES = sorted(SQL_DIR.rglob("*.sql"))


def has_subquery(text: str) -> bool:
    """True for "( SELECT" that is not the body of a CTE ("name AS (SELECT"), also across lines."""
    return any(
        not re.search(r"\bAS\s*$", text[: m.start()], re.IGNORECASE)
        for m in re.finditer(r"\(\s*SELECT\b", text, re.IGNORECASE)
    )


def test_the_sql_files_are_found():
    assert SQL_FILES, "No SQL files found"


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_sql_file_renders_without_leftover_placeholders(path):
    sql = render_sql(path)
    assert "${" not in sql
    assert "my-project" in sql


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_no_subquery_in_sql(path):
    text = path.read_text(encoding="utf-8")
    assert not has_subquery(text)
