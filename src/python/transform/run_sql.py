"""Run the SQL files of one layer in filename order (01_, 02_, ...).

Usage:
    python -m transform.run_sql bronze
    python -m transform.run_sql bronze --dry-run     # only print bytes processed (session 1)
    python -m transform.run_sql bronze --file 01_events_partitioned.sql
"""

import argparse

from google.cloud import bigquery

from common.config import SQL_DIR, render_sql, settings
from common.retry import call_with_retry

LAYERS = ("bronze",)  # Silver and Gold are built by dbt (see transform/run_dbt.py)


def run_layer(layer: str, dry_run: bool = False, only_file: str | None = None) -> None:
    client = bigquery.Client(project=settings().project)
    paths = sorted((SQL_DIR / layer).glob("*.sql"))
    if only_file:
        paths = [p for p in paths if p.name == only_file]
        if not paths:
            raise SystemExit(f"{only_file} not found in src/sql/{layer}/")

    for path in paths:
        config = bigquery.QueryJobConfig(dry_run=dry_run, use_query_cache=False)
        sql = render_sql(path)
        if dry_run:
            job = client.query(sql, job_config=config)
            print(f"{layer}/{path.name}: {job.total_bytes_processed:,} bytes")
        else:
            call_with_retry(lambda: client.query(sql, job_config=config).result())
            print(f"{layer}/{path.name}: done")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer", choices=LAYERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file")
    args = parser.parse_args()
    run_layer(args.layer, dry_run=args.dry_run, only_file=args.file)


if __name__ == "__main__":
    main()
