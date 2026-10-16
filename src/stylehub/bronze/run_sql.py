"""Run the SQL files of one layer in filename order (01_, 02_, ...).

Usage:
    python -m stylehub.bronze.run_sql bronze
    python -m stylehub.bronze.run_sql bronze --dry-run   # only print bytes processed
    python -m stylehub.bronze.run_sql bronze --file 01_events_partitioned.sql
"""

import argparse
import logging
from functools import partial

from google.cloud import bigquery

from stylehub.common.bq import query_config
from stylehub.common.config import SQL_DIR, Settings, resolve
from stylehub.common.retry import call_with_retry
from stylehub.common.sql import render_sql

log = logging.getLogger(__name__)

LAYERS = ("bronze",)  # Silver and Gold are built by dbt (see transform/run_dbt.py)


def run_query(client: bigquery.Client, sql: str, config: bigquery.QueryJobConfig) -> None:
    client.query(sql, job_config=config).result()


def run_layer(
    layer: str,
    dry_run: bool = False,
    only_file: str | None = None,
    client: bigquery.Client | None = None,
    cfg: Settings | None = None,
) -> None:
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
    paths = sorted((SQL_DIR / layer).glob("*.sql"))
    if only_file:
        paths = [p for p in paths if p.name == only_file]
        if not paths:
            raise FileNotFoundError(f"{only_file} not found in src/stylehub/sql/{layer}/")

    for path in paths:
        config = query_config(cfg, dry_run=dry_run, use_query_cache=False)
        sql = render_sql(path, cfg)
        if dry_run:
            job = client.query(sql, job_config=config)
            log.info("%s/%s: %s bytes", layer, path.name, f"{job.total_bytes_processed:,}")
        else:
            call_with_retry(partial(run_query, client, sql, config))
            log.info("%s/%s: done", layer, path.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer", choices=LAYERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        run_layer(args.layer, dry_run=args.dry_run, only_file=args.file)
    except FileNotFoundError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
