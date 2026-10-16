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
import json
import os
import shutil
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from stylehub.common.bq import query_config
from stylehub.common.config import DBT_DIR, ConfigError, Settings, resolve
from stylehub.common.retry import call_with_retry

# The gold tag also holds the test that compares Gold with Silver, so the silver step must skip it.
SELECTION = {
    "silver": ["--select", "tag:silver", "--exclude", "tag:gold"],
    "gold": ["--select", "tag:gold"],
    "all": [],
}


COMMANDS = ["build", "parse", "compile", "run", "test"]
NO_BIGQUERY_COMMANDS = {"parse"}  # these never read a table, so no snapshot date is needed
SNAPSHOT_TABLES = ("orders", "order_items", "products", "users")  # read by latest_bronze_snapshot
TARGETS = ["prod", "dev"]  # see dbt/profiles.yml
FAIL_FAST_COMMANDS = {"build", "run", "test"}  # parse and compile have no --fail-fast
DEFAULT_TIMEOUT_SECONDS = 3600  # one hour; set DBT_TIMEOUT_SECONDS to change it

RUN_RESULTS = DBT_DIR / "target" / "run_results.json"
BAD_STATUSES = {"error", "fail", "runtime error"}
MAX_LISTED = 5  # How many failed models and tests go in the error message.
# dbt never needs our secrets, so they are removed from its environment. A NAME PATTERN is used
# (not a fixed list): a new secret that follows the naming does not leak by being forgotten here.
# An allow-list would break dbt on Windows and in CI, where the needed variables differ a lot.
SECRET_NAME_PARTS = ("SECRET", "PASSWORD", "TOKEN", "WEBHOOK", "FERNET")
SECRET_NAME_PREFIXES = ("AIRFLOW",)
KEEP_ENV_NAMES = ("GOOGLE_APPLICATION_CREDENTIALS",)  # a path to a key file, dbt needs it


class DbtError(RuntimeError):
    """dbt is missing or a dbt command failed. The message says which model or test."""


def build_command(
    layer: str,
    command: str = "build",
    target: str = "prod",
    snapshot_dates: dict[str, str] | None = None,
) -> list[str]:
    """The dbt command line for one layer. dbt stops at the first failed model or test.

    snapshot_dates pins the Bronze snapshot each table is read from (see bronze_snapshot_dates).
    """
    if target not in TARGETS:
        raise ValueError(f"dbt target must be one of {TARGETS}, not {target!r}")
    fail_fast = ["--fail-fast"] if command in FAIL_FAST_COMMANDS else []
    pinned = (
        ["--vars", json.dumps({"bronze_snapshot_dates": snapshot_dates})] if snapshot_dates else []
    )
    return [
        "dbt",
        command,
        "--project-dir",
        str(DBT_DIR),
        "--profiles-dir",
        str(DBT_DIR),
        "--target",
        target,
        *pinned,
        *fail_fast,
        *SELECTION[layer],
    ]


def is_secret_name(name: str) -> bool:
    """True for a variable that dbt must not get (a password, token, webhook, Airflow setting)."""
    upper = name.upper()
    if upper in KEEP_ENV_NAMES:
        return False
    return upper.startswith(SECRET_NAME_PREFIXES) or any(
        part in upper for part in SECRET_NAME_PARTS
    )


def dbt_environment(cfg: Settings | None = None) -> dict[str, str]:
    """The current environment plus the names dbt reads in dbt/profiles.yml, without our secrets."""
    config = asdict(resolve(cfg))  # also loads secrets/.env
    env = {k: v for k, v in os.environ.items() if not is_secret_name(k)}
    env.update(
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
    return env


def timeout_seconds() -> int:
    """How long one dbt command may run. A stuck query must not hold the task for hours."""
    value = os.environ.get("DBT_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        seconds = int(value)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise ConfigError(f"DBT_TIMEOUT_SECONDS must be a whole number above 0, not {value!r}")
    return seconds


def failed_nodes(results_file: Path = RUN_RESULTS) -> list[str]:
    """The models and tests that failed in the last dbt run, like 'test.stylehub.x.1a2b: fail'."""
    try:
        results = json.loads(results_file.read_text(encoding="utf-8"))["results"]
    except (OSError, ValueError, KeyError):
        return []
    return [f"{r['unique_id']}: {r['status']}" for r in results if r.get("status") in BAD_STATUSES]


def result_summary(results_file: Path = RUN_RESULTS) -> dict[str, Any]:
    """Count the statuses of the last dbt run, like {"counts": {"pass": 40, "warn": 1}}.

    Saved in pipeline_runs.detail, because dbt/target is not kept after the run.
    """
    try:
        results = json.loads(results_file.read_text(encoding="utf-8"))["results"]
    except (OSError, ValueError, KeyError):
        return {}
    counts = Counter(str(r.get("status")) for r in results)
    warned = [r["unique_id"] for r in results if r.get("status") == "warn"]
    summary: dict[str, Any] = {"counts": dict(sorted(counts.items()))}
    if warned:
        summary["warned"] = warned[:MAX_LISTED]
    return summary


def newest_partition(client: bigquery.Client, cfg: Settings, table: str) -> date | None:
    """The newest partition day of one Bronze table, or None when it has no partition."""
    # Names come from our settings and a fixed list, never from a user.
    query = f"SELECT MAX(_PARTITIONDATE) AS d FROM `{cfg.project}.{cfg.bronze}.{table}`"  # noqa: S608

    def ask() -> list[bigquery.Row]:
        return list(client.query(query, job_config=query_config(cfg)).result())

    result: date | None = call_with_retry(ask)[0].d
    return result


def bronze_snapshot_dates(
    client: bigquery.Client | None = None, cfg: Settings | None = None
) -> dict[str, str]:
    """The newest Bronze snapshot day of each table, read ONCE, like {"orders": "2026-10-16"}.

    dbt gets these days as a variable, so every model and test of one run reads the same
    snapshot, and the days are saved in pipeline_runs.detail. Two compiles at different times
    can no longer produce different SQL for the same run. A table with no partition is an
    error: an empty Silver would pass every test and produce a Gold with zero revenue.
    """
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
    days: dict[str, str] = {}
    for table in SNAPSHOT_TABLES:
        newest = newest_partition(client, cfg, table)
        if newest is None:
            raise DbtError(
                f"Bronze table {cfg.bronze}.{table} has no partition. "
                "Run the ingest and bronze steps first."
            )
        days[table] = newest.isoformat()
    return days


def run_dbt(layer: str, command: str = "build", target: str = "prod") -> dict[str, Any]:
    """Run dbt for one layer and return the result counts. Raises DbtError if dbt fails."""
    if shutil.which("dbt") is None:
        raise DbtError("dbt is not installed. Run: uv sync --extra dbt")
    snapshots = None if command in NO_BIGQUERY_COMMANDS else bronze_snapshot_dates()
    RUN_RESULTS.unlink(missing_ok=True)  # so a failure never shows the result of an older run
    limit = timeout_seconds()
    try:
        result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            build_command(layer, command, target, snapshots), env=dbt_environment(), timeout=limit
        )
    except subprocess.TimeoutExpired:
        # dbt is stopped, but BigQuery jobs it already started may still finish on their own.
        raise DbtError(
            f"dbt {command} ({layer}, {target}) was stopped after {limit}s (DBT_TIMEOUT_SECONDS). "
            "Queries that had started may still run in BigQuery."
        ) from None
    if result.returncode != 0:
        failed = failed_nodes(RUN_RESULTS)
        detail = "; ".join(failed[:MAX_LISTED]) or "see the dbt log above"
        if len(failed) > MAX_LISTED:
            detail += f"; and {len(failed) - MAX_LISTED} more"
        raise DbtError(
            f"dbt {command} ({layer}, {target}) failed with exit code {result.returncode}: {detail}"
        )
    summary = result_summary(RUN_RESULTS)
    if snapshots:
        summary["bronze_snapshots"] = snapshots  # which Bronze day this run really read
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
