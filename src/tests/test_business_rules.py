"""Business rules live in Gold. These tests keep it that way (docs/ETL_VS_ELT.md).

When Finance changes what counts as revenue, you edit Gold and its check. Silver stays as it is.
"""

import re

from common.config import SQL_DIR

# status != 'Cancelled'   or   status NOT IN ('Cancelled', 'Returned')
STATUS_FILTER = re.compile(r"status\s*(?:!=|<>)\s*'[^']+'|status\s+NOT\s+IN\s*\([^)]*\)", re.I)


def status_filters(path):
    text = path.read_text(encoding="utf-8")
    return {" ".join(match.split()) for match in STATUS_FILTER.findall(text)}


def test_silver_does_not_filter_on_status():
    for path in (SQL_DIR / "silver").glob("*.sql"):
        assert not status_filters(path), f"{path.name} holds a business rule. Move it to Gold."


def test_revenue_rule_is_the_same_everywhere():
    """Gold tables and the Gold-vs-Silver check must use one rule, or the check fails."""
    rules = {}
    for layer in ("gold", "checks"):
        for path in (SQL_DIR / layer).glob("*.sql"):
            found = status_filters(path)
            if found:
                rules[f"{layer}/{path.name}"] = found
    assert rules, "expected at least one revenue rule"
    distinct = {frozenset(found) for found in rules.values()}
    assert len(distinct) == 1, f"The revenue rule differs between files: {rules}"
