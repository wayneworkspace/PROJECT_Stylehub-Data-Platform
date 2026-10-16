"""Checks on the dbt project that need no dbt install and no BigQuery."""

import json
import re
import subprocess
from pathlib import Path

import pytest

from stylehub.common.config import DBT_DIR, ConfigError
from stylehub.orchestration import run_daily
from stylehub.transform import run_dbt

FOLDERS = {  # model folder -> (dataset step, expected number of models)
    "staging": ("silver", 5),
    "intermediate": ("silver", 2),
    "marts/core": ("silver", 6),
    "marts/reporting": ("gold", 6),
}
NAME_PREFIXES = {  # model folder -> the names a model file may start with
    "staging": ("stg_stylehub__",),
    "intermediate": ("int_",),
    "marts/core": ("dim_", "fact_"),
}


def has_subquery(text: str) -> bool:
    """True for "( SELECT" that is not the body of a CTE ("name AS (SELECT"), also across lines."""
    return any(
        not re.search(r"\bAS\s*$", text[: m.start()], re.IGNORECASE)
        for m in re.finditer(r"\(\s*SELECT\b", text, re.IGNORECASE)
    )


def model_files(folder: str = "") -> list[Path]:
    return sorted((DBT_DIR / "models" / folder).rglob("*.sql"))


def project_config() -> dict:
    yaml = pytest.importorskip("yaml")
    text = (DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["models"]["stylehub"]


def test_each_folder_has_its_models():
    for folder, (_, count) in FOLDERS.items():
        assert len(model_files(folder)) == count, folder


@pytest.mark.parametrize("path", model_files(), ids=lambda p: p.name)
def test_model_follows_the_project_rules(path):
    text = path.read_text(encoding="utf-8")
    upper = text.upper()
    assert "CREATE " not in upper, "dbt creates the table, remove CREATE"
    assert not text.rstrip().endswith(";"), "remove the final ;"
    assert not has_subquery(text), "subquery"
    assert "${" not in text, "use ref() or source(), not ${...}"


NAMED_MODELS = [
    (path, prefixes) for folder, prefixes in NAME_PREFIXES.items() for path in model_files(folder)
]


@pytest.mark.parametrize(
    ("path", "prefixes"),
    NAMED_MODELS,
    ids=lambda value: value.name if isinstance(value, Path) else None,
)
def test_model_name_follows_the_dbt_labs_names(path, prefixes):
    assert path.name.startswith(prefixes), f"{path.name} should start with {prefixes}"


@pytest.mark.parametrize("path", model_files(), ids=lambda p: p.name)
def test_only_staging_reads_the_sources(path):
    """dbt Labs rule: source() is called in staging only. Every other model uses ref()."""
    text = path.read_text(encoding="utf-8")
    # latest_bronze_snapshot() is the staging macro that calls source() for the model.
    has_source = "source(" in text or "latest_bronze_snapshot(" in text
    assert has_source == ("staging" in path.parts)


@pytest.mark.parametrize("path", sorted((DBT_DIR / "models").rglob("*.y*ml")), ids=lambda p: p.name)
def test_yaml_file_is_named_like_dbt_labs(path):
    assert path.suffix == ".yaml" and path.name.startswith("_"), path.name
    assert path.name.endswith(("__models.yaml", "__sources.yaml", "__unit_tests.yaml")), path.name


def test_layer_tags_and_datasets_come_from_the_folder():
    """Tags and datasets are set per folder in dbt_project.yml, not in each model."""
    config = project_config()
    expected = {
        "staging": "silver",
        "intermediate": "silver",
        "core": "silver",
        "reporting": "gold",
    }
    folders = {
        "staging": config["staging"],
        "intermediate": config["intermediate"],
        "core": config["marts"]["core"],
        "reporting": config["marts"]["reporting"],
    }
    for name, step in expected.items():
        assert folders[name]["+tags"] == [step], name
    for path in model_files():
        assert "tags=" not in path.read_text(encoding="utf-8"), f"{path.name}: set tags per folder"


@pytest.mark.parametrize("path", sorted((DBT_DIR / "tests").glob("*.sql")), ids=lambda p: p.name)
def test_singular_test_has_a_layer_tag(path):
    """A test without a layer tag is skipped by the silver and gold steps."""
    text = path.read_text(encoding="utf-8")
    assert "tags=['silver']" in text or "tags=['gold']" in text


@pytest.mark.parametrize("path", sorted(DBT_DIR.rglob("*.sql")), ids=lambda p: p.name)
def test_refs_point_to_models_that_exist(path):
    names = {p.stem for p in model_files()}
    for name in re.findall(r"ref\('(\w+)'\)", path.read_text(encoding="utf-8")):
        assert name in names, f"ref('{name}') has no model"


def test_dbt_command_selects_one_layer():
    silver = run_dbt.build_command("silver")
    assert silver[:2] == ["dbt", "build"]
    assert "tag:silver" in silver
    assert "tag:gold" in silver  # it follows --exclude
    assert silver[silver.index("--exclude") + 1] == "tag:gold"
    assert run_dbt.build_command("gold")[-1] == "tag:gold"
    assert "--select" not in run_dbt.build_command("all")


def test_dbt_environment_uses_the_pipeline_settings(monkeypatch):
    monkeypatch.setenv("BQ_SILVER", "my_silver")
    env = run_dbt.dbt_environment()
    assert env["GCP_PROJECT_ID"] == "my-project"
    assert env["BQ_SILVER"] == "my_silver"
    assert env["BQ_GOLD"] == "stylehub_gold"


def test_missing_dbt_gives_a_clear_message(monkeypatch):
    monkeypatch.setattr(run_dbt.shutil, "which", lambda name: None)
    with pytest.raises(run_dbt.DbtError, match="uv sync --extra dbt"):
        run_dbt.run_dbt("silver")


def write_results(path, *pairs):
    results = [{"unique_id": uid, "status": status} for uid, status in pairs]
    path.write_text(json.dumps({"results": results}), encoding="utf-8")


def test_failed_nodes_lists_only_failed_models_and_tests(tmp_path):
    file = tmp_path / "run_results.json"
    write_results(
        file,
        ("model.stylehub.fact_orders", "success"),
        ("test.stylehub.gold_matches_silver", "fail"),
        ("model.stylehub.dim_users", "error"),
    )
    assert run_dbt.failed_nodes(file) == [
        "test.stylehub.gold_matches_silver: fail",
        "model.stylehub.dim_users: error",
    ]


def test_failed_nodes_is_empty_when_there_is_no_result_file(tmp_path):
    assert run_dbt.failed_nodes(tmp_path / "missing.json") == []


def test_a_failed_dbt_run_names_the_test_that_failed(monkeypatch, tmp_path):
    file = tmp_path / "run_results.json"
    monkeypatch.setattr(run_dbt, "RUN_RESULTS", file)
    monkeypatch.setattr(run_dbt.shutil, "which", lambda name: "dbt")

    def fake_dbt(command, env, timeout):
        write_results(file, ("test.stylehub.gold_matches_silver", "fail"))
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(run_dbt.subprocess, "run", fake_dbt)
    with pytest.raises(run_dbt.DbtError, match="gold_matches_silver: fail"):
        run_dbt.run_dbt("gold")


def test_steps_run_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_daily, "run_step", lambda run_id, name, func, d, alert=True: calls.append(name)
    )
    run_daily.run_steps("2026-10-01", "ingest", "gold")
    assert calls == ["ingest", "bronze", "silver", "gold"]


def test_build_stops_at_the_first_failure_but_parse_has_no_such_flag():
    assert "--fail-fast" in run_dbt.build_command("silver")
    assert "--fail-fast" in run_dbt.build_command("gold", "test")
    assert "--fail-fast" not in run_dbt.build_command("silver", "parse")
    assert run_dbt.build_command("gold")[-1] == "tag:gold"  # the selection stays last


def test_the_timeout_is_one_hour_unless_changed(monkeypatch):
    monkeypatch.delenv("DBT_TIMEOUT_SECONDS", raising=False)
    assert run_dbt.timeout_seconds() == 3600
    monkeypatch.setenv("DBT_TIMEOUT_SECONDS", "90")
    assert run_dbt.timeout_seconds() == 90


@pytest.mark.parametrize("value", ["abc", "0", "-5", ""])
def test_a_wrong_timeout_is_a_clear_error(monkeypatch, value):
    monkeypatch.setenv("DBT_TIMEOUT_SECONDS", value)
    with pytest.raises(ConfigError, match="DBT_TIMEOUT_SECONDS"):
        run_dbt.timeout_seconds()


def test_a_dbt_command_that_runs_too_long_is_stopped_with_a_clear_error(monkeypatch):
    monkeypatch.setattr(run_dbt.shutil, "which", lambda name: "dbt")
    monkeypatch.setenv("DBT_TIMEOUT_SECONDS", "7")
    seen = {}

    def slow_dbt(command, env, timeout):
        seen["timeout"] = timeout
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(run_dbt.subprocess, "run", slow_dbt)
    with pytest.raises(run_dbt.DbtError, match="stopped after 7s"):
        run_dbt.run_dbt("silver")
    assert seen["timeout"] == 7


def test_the_pipeline_uses_the_prod_target_by_default():
    command = run_dbt.build_command("silver")
    assert command[command.index("--target") + 1] == "prod"
    dev = run_dbt.build_command("silver", target="dev")
    assert dev[dev.index("--target") + 1] == "dev"
    assert run_dbt.build_command("gold")[-1] == "tag:gold"  # the selection stays last


def test_an_unknown_target_is_refused():
    with pytest.raises(ValueError, match="prod"):
        run_dbt.build_command("silver", target="staging")


def test_a_plain_dbt_build_by_hand_writes_to_dev_not_prod():
    yaml = pytest.importorskip("yaml")
    profile = yaml.safe_load((DBT_DIR / "profiles.yml").read_text(encoding="utf-8"))["stylehub"]
    assert profile["target"] == "dev"
    assert set(profile["outputs"]) == {"dev", "prod"}
    assert "BQ_SILVER" in profile["outputs"]["prod"]["dataset"]
    assert "BQ_SILVER" not in profile["outputs"]["dev"]["dataset"]


def test_every_target_has_a_cost_limit():
    yaml = pytest.importorskip("yaml")
    profile = yaml.safe_load((DBT_DIR / "profiles.yml").read_text(encoding="utf-8"))["stylehub"]
    for target in profile["outputs"].values():
        assert "maximum_bytes_billed" in target


def test_expected_schema_columns_are_all_read_by_the_staging_models():
    """EXPECTED_SCHEMAS (Python) and the staging SQL both list the columns: they must not drift."""
    from stylehub.ingestion.schema_check import EXPECTED_SCHEMAS

    for table, columns in EXPECTED_SCHEMAS.items():
        sql = (
            DBT_DIR / "models" / "staging" / "stylehub" / f"stg_stylehub__{table}.sql"
        ).read_text(encoding="utf-8")
        missing = [c for c in columns if not re.search(rf"\b{c}\b", sql)]
        assert not missing, f"stg_stylehub__{table}.sql does not read {missing}"


def test_dbt_gets_the_cost_limit_from_the_settings(monkeypatch):
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "777")
    assert run_dbt.dbt_environment()["BQ_MAX_BYTES_BILLED"] == "777"


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("ALERT_WEBHOOK_URL", True),
        ("AIRFLOW_ADMIN_PASSWORD", True),
        ("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", True),
        ("AIRFLOW_FERNET_KEY", True),
        ("GITHUB_TOKEN", True),
        ("SOMETHING_NEW_SECRET", True),
        ("GOOGLE_APPLICATION_CREDENTIALS", False),
        ("PATH", False),
        ("BQ_SILVER", False),
    ],
)
def test_secret_names_are_recognised_by_pattern(name, secret):
    assert run_dbt.is_secret_name(name) is secret


def test_dbt_does_not_get_the_secrets_of_the_pipeline(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://discord.example/secret")
    monkeypatch.setenv("AIRFLOW_ADMIN_PASSWORD", "x")
    monkeypatch.setenv("SOME_OTHER_SETTING", "kept")
    env = run_dbt.dbt_environment()
    assert "ALERT_WEBHOOK_URL" not in env and "AIRFLOW_ADMIN_PASSWORD" not in env
    assert env["SOME_OTHER_SETTING"] == "kept"  # PATH, HOME and the like must still reach dbt


def test_result_summary_counts_statuses_and_lists_warnings(tmp_path):
    file = tmp_path / "run_results.json"
    file.write_text(
        '{"results": [{"unique_id": "a", "status": "pass"}, {"unique_id": "b", "status": "pass"},'
        ' {"unique_id": "c", "status": "warn"}]}',
        encoding="utf-8",
    )
    assert run_dbt.result_summary(file) == {"counts": {"pass": 2, "warn": 1}, "warned": ["c"]}
    assert run_dbt.result_summary(tmp_path / "missing.json") == {}


REAL_SNAPSHOT_DATES = run_dbt.bronze_snapshot_dates  # the fixture below replaces the module's


# ---- the Bronze snapshot days are read once and pinned for the whole dbt run ----------------


@pytest.fixture(autouse=True)
def no_bigquery(monkeypatch):
    """run_dbt() reads the snapshot days from BigQuery: give it fixed days instead."""
    days = {"orders": "2026-10-16", "order_items": "2026-10-16", "products": "2026-10-15"}
    monkeypatch.setattr(run_dbt, "bronze_snapshot_dates", lambda *a, **k: days)
    return days


def test_the_command_pins_the_snapshot_days_as_a_dbt_variable():
    command = run_dbt.build_command("silver", snapshot_dates={"orders": "2026-10-16"})
    assert json.loads(command[command.index("--vars") + 1]) == {
        "bronze_snapshot_dates": {"orders": "2026-10-16"}
    }
    assert "--vars" not in run_dbt.build_command("silver")
    assert run_dbt.build_command("gold", snapshot_dates={"orders": "x"})[-1] == "tag:gold"


class FakeRows:
    def __init__(self, day):
        self.d = day


class FakeJob:
    def __init__(self, day):
        self.day = day

    def result(self):
        return [FakeRows(self.day)]


class FakeBigQuery:
    def __init__(self, days):
        self.days = days
        self.queries = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        table = sql.split("`")[1].rsplit(".", 1)[1]
        return FakeJob(self.days[table])


def test_snapshot_days_come_from_one_query_per_bronze_table():
    from datetime import date

    from stylehub.common.config import Settings

    cfg = Settings("p", "b", "raw", "src", "br", "sv", "gd", "op", "eu")
    days = dict.fromkeys(run_dbt.SNAPSHOT_TABLES, date(2026, 10, 16))
    client = FakeBigQuery(days)
    assert REAL_SNAPSHOT_DATES(client, cfg) == dict.fromkeys(run_dbt.SNAPSHOT_TABLES, "2026-10-16")
    assert len(client.queries) == len(run_dbt.SNAPSHOT_TABLES)
    assert all("`p.br." in q for q in client.queries)


def test_a_bronze_table_without_a_partition_stops_the_run():
    from datetime import date

    from stylehub.common.config import Settings

    cfg = Settings("p", "b", "raw", "src", "br", "sv", "gd", "op", "eu")
    days = dict.fromkeys(run_dbt.SNAPSHOT_TABLES, date(2026, 10, 16))
    days["users"] = None
    with pytest.raises(run_dbt.DbtError, match="users has no partition"):
        REAL_SNAPSHOT_DATES(FakeBigQuery(days), cfg)


def test_run_dbt_passes_the_days_to_dbt_and_reports_them(monkeypatch, no_bigquery):
    monkeypatch.setattr(run_dbt.shutil, "which", lambda name: "dbt")
    seen = {}

    def fake_dbt(command, env, timeout):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_dbt.subprocess, "run", fake_dbt)
    summary = run_dbt.run_dbt("silver")
    assert "--vars" in seen["command"]
    assert summary["bronze_snapshots"] == no_bigquery


def test_parse_does_not_need_bigquery(monkeypatch):
    monkeypatch.setattr(run_dbt.shutil, "which", lambda name: "dbt")
    monkeypatch.setattr(run_dbt, "bronze_snapshot_dates", lambda *a, **k: 1 / 0)
    seen = {}
    monkeypatch.setattr(
        run_dbt.subprocess,
        "run",
        lambda command, env, timeout: (
            seen.update(c=command) or subprocess.CompletedProcess(command, 0)
        ),
    )
    run_dbt.run_dbt("silver", "parse")
    assert "--vars" not in seen["c"]


# ---- unit tests and contracts ----------------------------------------------------------------


def unit_tests() -> list[dict]:
    yaml = pytest.importorskip("yaml")
    found = []
    for path in sorted((DBT_DIR / "models").rglob("*__unit_tests.yaml")):
        found += yaml.safe_load(path.read_text(encoding="utf-8"))["unit_tests"]
    return found


def test_there_are_unit_tests_for_the_gold_business_rules():
    models = {t["model"] for t in unit_tests()}
    assert {"daily_revenue", "monthly_revenue_by_category", "funnel_by_category"} <= models


@pytest.mark.parametrize("test", unit_tests(), ids=lambda t: t["name"])
def test_a_unit_test_has_a_layer_tag_and_a_model_that_exists(test):
    """Without a layer tag the gold step would skip the unit test."""
    assert test["config"]["tags"] in (["silver"], ["gold"])
    assert test["model"] in {p.stem for p in model_files()}
    assert test.get("description"), "say which rule the test protects"


def test_published_gold_tables_have_a_contract_with_types():
    yaml = pytest.importorskip("yaml")
    text = (DBT_DIR / "models" / "marts" / "reporting" / "_reporting__models.yaml").read_text(
        encoding="utf-8"
    )
    for model in yaml.safe_load(text)["models"]:
        if model["name"] == "daily_events_by_type":  # incremental: no contract yet (see the yaml)
            continue
        assert model["config"]["contract"]["enforced"] is True, model["name"]
        assert all("data_type" in column for column in model["columns"]), model["name"]
