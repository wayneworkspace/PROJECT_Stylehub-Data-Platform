"""Run the whole pipeline for one date, step by step. Each step is its own function.

When moving to Airflow later, each entry in STEPS becomes a task,
with no change to the logic inside.

Usage: python -m pipeline.run_daily --date 2026-10-01
"""

import argparse

from ingestion.incremental import INCREMENTAL_TABLES, ingest_table
from pipeline.checks import run_checks
from pipeline.load_bronze import TABLES, load_day
from pipeline.run_sql import run_layer


def step_ingest(data_date: str) -> None:
    for table in INCREMENTAL_TABLES:
        print(ingest_table(table, data_date))


def step_bronze(data_date: str) -> None:
    for table in TABLES:
        print(f"{table}: {load_day(table, data_date)} rows")


def step_silver(data_date: str) -> None:
    run_layer("silver")


def step_gold(data_date: str) -> None:
    run_layer("gold")


def step_checks(data_date: str) -> None:
    if not run_checks():
        raise SystemExit("Data checks failed")


STEPS = [
    ("ingest", step_ingest),
    ("bronze", step_bronze),
    ("silver", step_silver),
    ("gold", step_gold),
    ("checks", step_checks),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--from-step", choices=[name for name, _ in STEPS], default="ingest")
    args = parser.parse_args()

    names = [name for name, _ in STEPS]
    for name, func in STEPS[names.index(args.from_step) :]:
        print(f"== {name} ==")
        func(args.date)


if __name__ == "__main__":
    main()
