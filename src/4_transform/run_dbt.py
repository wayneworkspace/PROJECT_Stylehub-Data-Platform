"""Build Silver or Gold with dbt; failed tests fail the step."""

from collections import Counter
from importlib import import_module
from typing import Any

config = import_module("src.1_source.config")

BAD_STATUSES = {"error", "fail", "runtime error"}
MAX_LISTED = 5  # How many failed models and tests go in the error message.


class DbtError(RuntimeError):
    """A dbt build failed. The message says which model or test."""


def build_command(layer: str) -> list[str]:
    """dbt build arguments for one layer, stopping at the first failure."""
    project = str(config.DBT_DIR)
    # Own target and log folders, so the two branches can run dbt at once.
    output = config.DBT_DIR / "target" / layer
    logs = config.ROOT / "logs" / "dbt" / layer
    return [
        "build",
        "--project-dir",
        project,
        "--profiles-dir",
        project,
        "--target-path",
        str(output),
        "--log-path",
        str(logs),
        "--fail-fast",
        # A test runs only when all its models are selected (Gold checks wait for Gold).
        "--indirect-selection",
        "cautious",
        "--select",
        f"tag:{layer}",
        # Static course events are built by hand, not nightly (fact_events.sql).
        "--exclude",
        "tag:events",
    ]


def run_dbt(layer: str) -> dict[str, Any]:
    """Build one layer; return result counts or raise DbtError."""
    from dbt.cli.main import dbtRunner  # slow to import, so only the dbt steps pay for it

    # dbt reads secrets/.env values that config.settings() already loaded.
    outcome = dbtRunner().invoke(build_command(layer))
    results = getattr(outcome.result, "results", [])
    statuses = [(r.node.unique_id, str(getattr(r.status, "value", r.status))) for r in results]
    if not outcome.success:
        failed = [f"{name}: {status}" for name, status in statuses if status in BAD_STATUSES]
        detail = "; ".join(failed[:MAX_LISTED]) or str(outcome.exception or "see the dbt log above")
        if len(failed) > MAX_LISTED:
            detail += f"; and {len(failed) - MAX_LISTED} more"
        raise DbtError(f"dbt build ({layer}) failed: {detail}")
    counts = Counter(status for _, status in statuses)
    summary: dict[str, Any] = {"counts": dict(sorted(counts.items()))} if counts else {}
    warned = [name for name, status in statuses if status == "warn"]
    if warned:
        summary["warned"] = warned[:MAX_LISTED]
    return summary
