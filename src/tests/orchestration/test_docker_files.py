"""The Docker files: one compose file, every Dockerfile it names exists, profiles are set."""

import re

import pytest

from common.config import ROOT

yaml = pytest.importorskip("yaml")

COMPOSE = ROOT / "docker-compose.yaml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_every_service_has_a_profile(compose):
    """Nothing starts by itself, so `docker compose up postgres` never starts Airflow."""
    for name, service in compose["services"].items():
        assert service.get("profiles"), f"{name} has no profile"


def test_airflow_services_use_the_airflow_profile(compose):
    for name, service in compose["services"].items():
        if name.startswith("airflow"):
            assert service["profiles"] == ["airflow"], name


def test_the_dockerfiles_named_in_compose_exist(compose):
    for name, service in compose["services"].items():
        build = service.get("build")
        if build:
            assert (ROOT / build["dockerfile"]).is_file(), f"{name}: {build['dockerfile']}"


def test_compose_has_no_required_variable():
    """`${VAR:?}` is checked for every service, even one that is not started."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert not re.search(r"(?<!\$)\$\{[^}]*:\?", text)  # "$${...}" is a shell variable: fine


def test_the_old_split_files_are_gone():
    assert not (ROOT / "Dockerfile").exists()
    assert not (ROOT / "airflow" / "docker-compose.yaml").exists()


def test_deploy_folder_layout():
    """Everything that runs (Docker, Airflow, VM script) lives in deploy/, one folder per part."""
    deploy = ROOT / "deploy"
    assert (deploy / "pipeline" / "Dockerfile").is_file()
    assert (deploy / "pipeline" / "run_on_vm.sh").is_file()
    assert (deploy / "airflow" / "Dockerfile").is_file()
    assert (deploy / "airflow" / "dags" / "stylehub_daily.py").is_file()
    assert (ROOT / "dev" / "postgres" / "init" / "01_seed.sql").is_file()
    for old in ("docker", "deploy/docker", "deploy/vm", "deploy/postgres", "airflow/dags",
                "airflow/Dockerfile"):
        assert not (ROOT / old).exists(), old
    assert (ROOT / "docs" / "assets").is_dir()
    assert (ROOT / "docs" / "html" / "architecture.html").is_file()
    assert not (ROOT / "assets").exists()


def test_optional_ingestion_is_not_used_by_run_daily():
    """Postgres and API code sits in ingestion/optional, and the daily run never imports it."""
    optional = ROOT / "src" / "python" / "ingestion" / "optional"
    for name in ("database.py", "api.py"):
        assert (optional / name).is_file()
    assert (optional / "sources" / "postgres.py").is_file()
    assert not (ROOT / "src" / "python" / "sources").exists()
    run_daily = (ROOT / "src" / "python" / "orchestration" / "run_daily.py").read_text("utf-8")
    imports = [line for line in run_daily.splitlines() if line.startswith(("import ", "from "))]
    assert not [line for line in imports if "optional" in line]


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


def test_relative_links_in_the_docs_point_to_real_files():
    link = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
    docs = ROOT / "docs"
    pages = [ROOT / "README.md", docs / "README.md", ROOT / "dbt" / "README.md",
             ROOT / "deploy" / "airflow" / "README.md"]
    pages += sorted((docs / "design").glob("*.md")) + sorted((docs / "ops").glob("*.md"))
    broken = []
    for page in pages:
        for target in link.findall(page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (page.parent / target).exists():
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    assert not broken, broken
