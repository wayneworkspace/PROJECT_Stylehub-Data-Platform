"""Business rules live in Gold. These tests keep it that way (docs/design/ETL_VS_ELT.md).

When Finance changes what counts as revenue, you edit Gold and its test. Silver stays as it is.
The rules are in the dbt models and tests (dbt/).
"""

import re

import pytest

from stylehub.common.config import DBT_DIR

# status != 'Cancelled'   or   status NOT IN ('Cancelled', 'Returned')
STATUS_FILTER = re.compile(r"status\s*(?:!=|<>)\s*'[^']+'|status\s+NOT\s+IN\s*\([^)]*\)", re.I)

SILVER_FOLDERS = ("staging", "intermediate", "marts/core")  # see tags in dbt_project.yml
GOLD_FOLDERS = ("marts/reporting",)


def models_in(folders):
    return sorted(p for folder in folders for p in (DBT_DIR / "models" / folder).rglob("*.sql"))


def status_filters(path):
    text = path.read_text(encoding="utf-8")
    return {" ".join(match.split()) for match in STATUS_FILTER.findall(text)}


@pytest.mark.parametrize("folder", SILVER_FOLDERS + GOLD_FOLDERS)
def test_every_model_folder_is_found(folder):
    """A wrong folder name would make the tests below check nothing and always pass."""
    assert models_in([folder]), f"no models found in dbt/models/{folder}"


@pytest.mark.parametrize("path", models_in(SILVER_FOLDERS), ids=lambda p: p.name)
def test_silver_does_not_filter_on_status(path):
    assert not status_filters(path), f"{path.name} holds a business rule. Move it to Gold."


MACRO = "revenue_order_filter"


def test_revenue_rule_is_written_once_and_used_everywhere():
    """Gold models and the Gold-vs-Silver test all call ONE macro, so the rule cannot drift."""
    users = [
        DBT_DIR / "models" / "marts" / "reporting" / name
        for name in (
            "daily_revenue.sql",
            "monthly_revenue_by_category.sql",
        )
    ] + [DBT_DIR / "tests" / "gold_matches_silver.sql"]
    for path in users:
        text = path.read_text(encoding="utf-8")
        assert MACRO in text, f"{path.name} must use the macro {MACRO}"
        assert not status_filters(path), f"{path.name} holds its own status filter"


def test_silver_does_not_use_the_revenue_macro():
    for path in models_in(SILVER_FOLDERS):
        assert MACRO not in path.read_text(encoding="utf-8"), f"{path.name} holds a Gold rule"


def test_the_macro_reads_its_statuses_from_one_variable():
    macro = (DBT_DIR / "macros" / "revenue_order_filter.sql").read_text(encoding="utf-8")
    project = (DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8")
    assert "revenue_excluded_statuses" in macro and "revenue_excluded_statuses" in project
