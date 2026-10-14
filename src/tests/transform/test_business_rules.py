"""Business rules live in Gold. These tests keep it that way (docs/ETL_VS_ELT.md).

When Finance changes what counts as revenue, you edit Gold and its test. Silver stays as it is.
The rules are in the dbt models and tests (dbt/).
"""

import re

from common.config import DBT_DIR

# status != 'Cancelled'   or   status NOT IN ('Cancelled', 'Returned')
STATUS_FILTER = re.compile(r"status\s*(?:!=|<>)\s*'[^']+'|status\s+NOT\s+IN\s*\([^)]*\)", re.I)


def status_filters(path):
    text = path.read_text(encoding="utf-8")
    return {" ".join(match.split()) for match in STATUS_FILTER.findall(text)}


def test_silver_does_not_filter_on_status():
    for path in (DBT_DIR / "models" / "silver").glob("*.sql"):
        assert not status_filters(path), f"{path.name} holds a business rule. Move it to Gold."


def test_revenue_rule_is_the_same_everywhere():
    """Gold models and the Gold-vs-Silver test must use one rule, or the test fails."""
    paths = list((DBT_DIR / "models" / "gold").glob("*.sql")) + [
        DBT_DIR / "tests" / "gold_matches_silver.sql"
    ]
    rules = {path.name: status_filters(path) for path in paths if status_filters(path)}
    assert rules, "expected at least one revenue rule"
    distinct = {frozenset(found) for found in rules.values()}
    assert len(distinct) == 1, f"The revenue rule differs between files: {rules}"
