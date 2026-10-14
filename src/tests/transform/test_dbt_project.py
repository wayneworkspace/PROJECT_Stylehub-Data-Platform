"""Checks on the dbt project that need no dbt install and no BigQuery."""

import re
from pathlib import Path

import pytest

from common.config import DBT_DIR
from orchestration import run_daily
from transform import run_dbt

FOLDERS = {  # model folder -> (dataset step, expected number of models)
    "staging": ("silver", 5),
    "intermediate": ("silver", 2),
    "marts/core": ("silver", 6),
    "marts/reporting": ("gold", 6),
}


def model_files(folder: str = "") -> list[Path]:
    return sorted((DBT_DIR / "models" / folder).rglob("*.sql"))


def project_config() -> dict:
    yaml = pytest.importorskip("yaml")
    text = (DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["models"]["stylehub"]


def test_each_folder_has_its_models():
    for folder, (_, count) in FOLDERS.items():
        assert len(model_files(folder)) == count, folder


def test_models_follow_the_project_rules():
    for path in model_files():
        text = path.read_text(encoding="utf-8")
        upper = text.upper()
        assert "CREATE " not in upper, f"{path.name}: dbt creates the table, remove CREATE"
        assert not text.rstrip().endswith(";"), f"{path.name}: remove the final ;"
        assert "(SELECT" not in upper.replace("( SELECT", "(SELECT"), f"{path.name}: subquery"
        assert "${" not in text, f"{path.name}: use ref() or source(), not ${{...}}"


def test_folders_follow_the_dbt_labs_names():
    for path in model_files("staging"):
        assert path.name.startswith("stg_stylehub__"), path.name
    for path in model_files("intermediate"):
        assert path.name.startswith("int_"), path.name
    for path in model_files("marts/core"):
        assert path.name.startswith(("dim_", "fact_")), path.name


def test_only_staging_reads_the_sources():
    """dbt Labs rule: source() is called in staging only. Every other model uses ref()."""
    for path in model_files():
        has_source = "source(" in path.read_text(encoding="utf-8")
        assert has_source == ("staging" in path.parts), path.name


def test_yaml_files_are_named_like_dbt_labs():
    for path in (DBT_DIR / "models").rglob("*.y*ml"):
        assert path.suffix == ".yaml" and path.name.startswith("_"), path.name
        assert path.name.endswith(("__models.yaml", "__sources.yaml")), path.name


def test_layer_tags_and_datasets_come_from_the_folder():
    """Tags and datasets are set per folder in dbt_project.yml, not in each model."""
    config = project_config()
    expected = {
        "staging": "silver",
        "intermediate": "silver",
        "core": "silver",
        "reporting": "gold",
    }
    folders = {"staging": config["staging"], "intermediate": config["intermediate"],
               "core": config["marts"]["core"], "reporting": config["marts"]["reporting"]}
    for name, step in expected.items():
        assert folders[name]["+tags"] == [step], name
    for path in model_files():
        assert "tags=" not in path.read_text(encoding="utf-8"), f"{path.name}: set tags per folder"


def test_singular_tests_have_a_layer_tag():
    """A test without a layer tag is skipped by the silver and gold steps."""
    for path in (DBT_DIR / "tests").glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        assert "tags=['silver']" in text or "tags=['gold']" in text, path.name


def test_refs_point_to_models_that_exist():
    names = {p.stem for p in model_files()}
    for path in DBT_DIR.rglob("*.sql"):
        for name in re.findall(r"ref\('(\w+)'\)", path.read_text(encoding="utf-8")):
            assert name in names, f"{path.name}: ref('{name}') has no model"


def test_dbt_command_selects_one_layer():
    silver = run_dbt.build_command("silver")
    assert silver[:2] == ["dbt", "build"]
    assert "tag:silver" in silver
    assert "tag:gold" in silver  # it follows --exclude
    assert silver[silver.index("--exclude") + 1] == "tag:gold"
    assert run_dbt.build_command("gold")[-1] == "tag:gold"
    assert "--select" not in run_dbt.build_command("all")


def test_dbt_environment_uses_the_pipeline_settings(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    monkeypatch.setenv("BQ_SILVER", "my_silver")
    env = run_dbt.dbt_environment()
    assert env["GCP_PROJECT_ID"] == "my-project"
    assert env["BQ_SILVER"] == "my_silver"
    assert env["BQ_GOLD"] == "stylehub_gold"


def test_missing_dbt_gives_a_clear_message(monkeypatch):
    monkeypatch.setattr(run_dbt.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="uv sync --extra dbt"):
        run_dbt.run_dbt("silver")


def test_steps_run_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(run_daily, "run_step", lambda run_id, name, func, d: calls.append(name))
    run_daily.run_steps("2026-10-01", "ingest", "gold")
    assert calls == ["ingest", "bronze", "silver", "gold"]
