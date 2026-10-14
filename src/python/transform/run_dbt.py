"""Run dbt for the Silver and Gold layers. The dbt project lives in the dbt/ folder.

dbt builds the models and runs their tests in one command. A failed test fails the step.

Usage:
    python -m transform.run_dbt silver
    python -m transform.run_dbt gold
    python -m transform.run_dbt all
    python -m transform.run_dbt silver --command parse       # only check the project, no BigQuery
"""

import argparse
import os
import shutil
import subprocess
from dataclasses import asdict

from common.config import DBT_DIR, settings

# The gold tag also holds the test that compares Gold with Silver, so the silver step must skip it.
SELECTION = {
    "silver": ["--select", "tag:silver", "--exclude", "tag:gold"],
    "gold": ["--select", "tag:gold"],
    "all": [],
}


COMMANDS = ["build", "parse", "compile", "run", "test"]


def build_command(layer: str, command: str = "build") -> list[str]:
    """The dbt command line for one layer."""
    return [
        "dbt",
        command,
        "--project-dir",
        str(DBT_DIR),
        "--profiles-dir",
        str(DBT_DIR),
        *SELECTION[layer],
    ]


def dbt_environment() -> dict[str, str]:
    """The current environment plus the names dbt reads in dbt/profiles.yml."""
    config = asdict(settings())  # also loads secrets/.env
    env = os.environ.copy()
    env.update(
        {
            "GCP_PROJECT_ID": config["project"],
            "GCP_LOCATION": config["location"],
            "BQ_BRONZE": config["bronze"],
            "BQ_SILVER": config["silver"],
            "BQ_GOLD": config["gold"],
        }
    )
    return env


def run_dbt(layer: str, command: str = "build") -> None:
    """Run dbt for one layer. Raises an error if dbt fails (a model or a test)."""
    if shutil.which("dbt") is None:
        raise SystemExit("dbt is not installed. Run: uv sync --extra dbt")
    subprocess.run(build_command(layer, command), env=dbt_environment(), check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer", choices=list(SELECTION))
    parser.add_argument("--command", default="build", choices=COMMANDS)
    args = parser.parse_args()
    run_dbt(args.layer, args.command)


if __name__ == "__main__":
    main()
