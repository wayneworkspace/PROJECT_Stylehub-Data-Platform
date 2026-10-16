import pytest

from stylehub.bronze import run_sql


def test_a_missing_sql_file_is_an_error_not_an_exit(monkeypatch):
    monkeypatch.setattr(run_sql.bigquery, "Client", lambda project: object())
    with pytest.raises(FileNotFoundError, match="nope.sql"):
        run_sql.run_layer("bronze", only_file="nope.sql")
