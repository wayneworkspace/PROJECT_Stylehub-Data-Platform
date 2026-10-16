"""The rule: every pipeline step runs through run_step, so it is logged, recorded and alerted.

The first test runs the steps and looks at what happened. The others read the code with `ast`
(the syntax tree), not as text, so renaming a variable or adding a space cannot break them and
nobody can add a shortcut around run_step. They need neither Airflow nor BigQuery.
"""

import ast
from pathlib import Path

from stylehub.common.config import ROOT
from stylehub.orchestration import run_daily

PACKAGE = ROOT / "src" / "stylehub"
DAG_FILE = ROOT / "deploy" / "airflow" / "dags" / "stylehub_daily.py"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_every_step_that_runs_is_recorded_once(monkeypatch):
    ran, recorded = [], []
    steps = [(name, lambda d, name=name: ran.append(name)) for name, _ in run_daily.STEPS]
    monkeypatch.setattr(run_daily, "STEPS", steps)
    monkeypatch.setattr(run_daily, "record_run", recorded.append)
    monkeypatch.setattr(run_daily, "send_alert", lambda text: None)

    run_daily.run_steps("2026-10-01", "ingest", "gold", run_id="r1")

    assert ran == [name for name, _ in steps] == ["ingest", "bronze", "silver", "gold"]
    assert [row["step"] for row in recorded] == ran
    assert {row["run_id"] for row in recorded} == {"r1"}


def names_used(tree: ast.AST) -> set[str]:
    """Every variable and attribute name that the code uses (not the strings or comments)."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return found


def test_step_functions_are_used_only_inside_run_daily():
    names = {func.__name__ for _, func in run_daily.STEPS}
    assert len(names) == 4
    for path in PACKAGE.rglob("*.py"):
        if path.name == "run_daily.py":
            continue
        shortcut = names & names_used(parse(path))
        assert not shortcut, f"{path.name} uses {sorted(shortcut)} without run_step"


def stylehub_imports(path: Path) -> set[str]:
    """Every 'from stylehub... import name' in a file, as 'module.name'."""
    found = set()
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("stylehub"):
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names if a.name.startswith("stylehub")}
    return found


def test_the_airflow_dag_reaches_the_pipeline_only_through_run_daily():
    # It may import nothing else from the project: no load_bronze, run_dbt or csv_tables.
    assert stylehub_imports(DAG_FILE) == {"stylehub.orchestration.run_daily"}


def calls_to(tree: ast.AST, owner: str, method: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == owner
    ]


def test_both_kinds_of_dag_task_call_run_daily():
    tree = parse(DAG_FILE)
    assert calls_to(tree, "run_daily", "run_steps")  # the Python tasks (ingest, bronze)
    text = DAG_FILE.read_text(encoding="utf-8")
    assert "python -m stylehub.orchestration.run_daily" in text  # the dbt tasks (silver, gold)
