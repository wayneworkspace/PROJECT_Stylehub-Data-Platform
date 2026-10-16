"""Run dbt for the Silver and Gold layers. The dbt project lives in the dbt/ folder.

dbt builds the models and runs their tests in one command. A failed test fails the step.

The pipeline writes to the real datasets (dbt target "prod"). To try something without touching
them, use --target dev: dbt then writes to dbt_<DBT_DEV_USER>_stylehub_silver and ..._gold.

Usage:
    python -m stylehub.transform.run_dbt silver --target dev
    python -m stylehub.transform.run_dbt gold
    python -m stylehub.transform.run_dbt all
    python -m stylehub.transform.run_dbt silver --command parse   # only check, no BigQuery
"""

import argparse
import os
from collections import Counter
from typing import Any

from stylehub.common.config import DBT_DIR, Settings, resolve

# The gold tag also holds the test that compares Gold with Silver, so the silver step must skip it.
SELECTION = {
    "silver": ["--select", "tag:silver", "--exclude", "tag:gold"],
    "gold": ["--select", "tag:gold"],
    "all": [],
}
COMMANDS = ["build", "parse", "compile", "run", "test"]
TARGETS = ["prod", "dev"]  # see dbt/profiles.yml
FAIL_FAST_COMMANDS = {"build", "run", "test"}  # parse and compile have no --fail-fast
BAD_STATUSES = {"error", "fail", "runtime error"}
MAX_LISTED = 5  # How many failed models and tests go in the error message.


class DbtError(RuntimeError):
    """dbt is missing or a dbt command failed. The message says which model or test."""


def build_command(layer: str, command: str = "build", target: str = "prod") -> list[str]:
    """The dbt arguments for one layer. dbt stops at the first failed model or test."""
    if target not in TARGETS:
        raise ValueError(f"dbt target must be one of {TARGETS}, not {target!r}")
    fail_fast = ["--fail-fast"] if command in FAIL_FAST_COMMANDS else []
    return [
        command,
        "--project-dir",
        str(DBT_DIR),
        "--profiles-dir",
        str(DBT_DIR),
        "--target",
        target,
        *fail_fast,
        *SELECTION[layer],
    ]


def export_settings(cfg: Settings | None = None) -> None:
    """Put the pipeline settings in the environment, where dbt/profiles.yml reads them."""
    config = resolve(cfg).model_dump()  # also loads secrets/.env
    os.environ.update(
        {
            "GCP_PROJECT_ID": config["project"],
            "GCP_LOCATION": config["location"],
            "BQ_BRONZE": config["bronze"],
            "BQ_STAGING": config["staging"],
            "BQ_SILVER": config["silver"],
            "BQ_GOLD": config["gold"],
            "BQ_MAX_BYTES_BILLED": str(config["max_bytes_billed"]),
        }
    )


def run_dbt(layer: str, command: str = "build", target: str = "prod") -> dict[str, Any]:
    """Run dbt for one layer and return the result counts. Raises DbtError if dbt fails."""
    try:
        from dbt.cli.main import dbtRunner
    except ImportError:
        raise DbtError("dbt is not installed. Run: uv sync --extra dbt") from None
    export_settings()
    outcome = dbtRunner().invoke(build_command(layer, command, target))
    results = getattr(outcome.result, "results", [])  # parse and compile have no results
    statuses = [(r.node.unique_id, str(getattr(r.status, "value", r.status))) for r in results]
    if not outcome.success:
        failed = [f"{name}: {status}" for name, status in statuses if status in BAD_STATUSES]
        detail = "; ".join(failed[:MAX_LISTED]) or str(outcome.exception or "see the dbt log above")
        if len(failed) > MAX_LISTED:
            detail += f"; and {len(failed) - MAX_LISTED} more"
        raise DbtError(f"dbt {command} ({layer}, {target}) failed: {detail}")
    counts = Counter(status for _, status in statuses)
    summary: dict[str, Any] = {"counts": dict(sorted(counts.items()))} if counts else {}
    warned = [name for name, status in statuses if status == "warn"]
    if warned:
        summary["warned"] = warned[:MAX_LISTED]
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer", choices=list(SELECTION))
    parser.add_argument("--command", default="build", choices=COMMANDS)
    parser.add_argument("--target", default="prod", choices=TARGETS)
    args = parser.parse_args()
    try:
        run_dbt(args.layer, args.command, args.target)
    except DbtError as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
