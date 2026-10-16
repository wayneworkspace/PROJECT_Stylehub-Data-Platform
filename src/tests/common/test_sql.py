import pytest

from stylehub.common.sql import render_sql


def test_placeholders_are_filled_from_the_settings(tmp_path):
    sql = tmp_path / "01_x.sql"
    sql.write_text("SELECT 1 FROM `${project}.${bronze}.orders`", encoding="utf-8")
    assert render_sql(sql) == "SELECT 1 FROM `my-project.stylehub_bronze.orders`"


def test_an_unknown_placeholder_is_an_error_before_bigquery_sees_it(tmp_path):
    sql = tmp_path / "01_x.sql"
    sql.write_text("SELECT 1 FROM `${project}.${bronse}.orders`", encoding="utf-8")
    with pytest.raises(KeyError, match="bronse"):
        render_sql(sql)
