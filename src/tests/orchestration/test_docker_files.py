"""The Docker files: one compose file, every Dockerfile it names exists, profiles are set."""

import re

import pytest

from stylehub.common.config import ROOT

PACKAGE = ROOT / "src" / "stylehub"

yaml = pytest.importorskip("yaml")

COMPOSE = ROOT / "docker-compose.yaml"
SERVICES = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_compose_has_services():
    assert SERVICES, "no service found in docker-compose.yaml"


@pytest.mark.parametrize("name", SERVICES)
def test_every_service_has_a_profile(name):
    """Nothing starts by itself, so `docker compose up` alone never starts a container."""
    assert SERVICES[name].get("profiles"), f"{name} has no profile"


@pytest.mark.parametrize("name", [name for name in SERVICES if name.startswith("airflow")])
def test_airflow_services_use_the_airflow_profile(name):
    assert SERVICES[name]["profiles"] == ["airflow"]


BUILT_SERVICES = [name for name, service in SERVICES.items() if service.get("build")]


@pytest.mark.parametrize("name", BUILT_SERVICES)
def test_the_dockerfile_named_in_compose_exists(name):
    dockerfile = SERVICES[name]["build"]["dockerfile"]
    assert (ROOT / dockerfile).is_file(), f"{name}: {dockerfile}"


def test_compose_has_no_required_variable():
    """`${VAR:?}` is checked for every service, even one that is not started."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert not re.search(r"(?<!\$)\$\{[^}]*:\?", text)  # "$${...}" is a shell variable: fine


def test_deploy_folder_layout():
    """Everything that runs (Docker, Airflow, VM script) lives in deploy/, one folder per part."""
    deploy = ROOT / "deploy"
    assert (deploy / "pipeline" / "Dockerfile").is_file()
    assert (deploy / "pipeline" / "run_on_vm.sh").is_file()
    assert (deploy / "airflow" / "Dockerfile").is_file()
    assert (deploy / "airflow" / "dags" / "stylehub_daily.py").is_file()
    assert (ROOT / "docs" / "assets").is_dir()
    assert (ROOT / "docs" / "html" / "architecture.html").is_file()


def test_unused_ingestion_code_is_not_kept_in_the_package():
    """The Postgres and API sources never ran on a real source. They were moved to to_delete/."""
    assert not (PACKAGE / "ingestion" / "optional").exists()
    assert not (PACKAGE / "sources").exists()
    assert not (ROOT / "dev" / "postgres").exists()


def test_the_airflow_services_do_not_mount_the_project_folder():
    """The code comes from the image, so laptop and VM run the same thing."""
    for name in (n for n in SERVICES if n.startswith("airflow")):
        for volume in SERVICES[name].get("volumes", []):
            assert not str(volume).startswith(".:"), f"{name} mounts the whole project folder"
    common = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["x-airflow-common"]
    assert not [v for v in common["volumes"] if str(v).startswith(".:")]


def test_one_env_example_names_every_compose_variable():
    """One .env.example for everything: each ${AIRFLOW_...} in compose is listed in it."""
    assert not (ROOT / "deploy" / "airflow" / ".env.example").exists()
    names = set(re.findall(r"\$\{(AIRFLOW_[A-Z][A-Z_]*)", COMPOSE.read_text(encoding="utf-8")))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    listed = set(re.findall(r"^(AIRFLOW_[A-Z_]+)=", example, flags=re.MULTILINE))
    assert names, "compose should read some AIRFLOW_ variables"
    assert names <= listed, f"missing in .env.example: {sorted(names - listed)}"


def test_docs_are_grouped_by_purpose():
    """docs/design says why, docs/ops says how to run it; no page sits loose in docs/."""
    groups = {
        "design": ("ARCHITECTURE", "DECISIONS", "ETL_VS_ELT", "EXTENDING", "ROADMAP"),
        "ops": ("RUN_END_TO_END", "DEVOPS", "CD", "DEPLOY_VM"),
    }
    for folder, names in groups.items():
        for name in names:
            assert (ROOT / "docs" / folder / f"{name}.md").is_file(), name
            assert not (ROOT / "docs" / f"{name}.md").exists(), name
