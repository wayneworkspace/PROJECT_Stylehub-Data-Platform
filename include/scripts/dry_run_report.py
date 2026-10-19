"""Bytes each query would scan, from BigQuery dry runs (free); prints Markdown.

Usage: uv run python include/scripts/dry_run_report.py
Estimates include partition and cluster pruning; the real bill can be lower.
"""

import os
import sys
from importlib import import_module
from pathlib import Path
from string import Template

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")

COLUMNS = "SELECT event_type, product_id, price FROM `${project}.${bronze}.events_partitioned`"
# Buổi 1: the same events question with and without partition and cluster filters.
QUERIES = {
    "events, all columns, no filter": "SELECT * FROM `${project}.${bronze}.events_partitioned`",
    "events, 3 columns, no filter": COLUMNS,
    "events, 3 columns, one day": COLUMNS + " WHERE DATE(event_time) = '2019-11-15'",
    "events, 3 columns, one day, purchases": (
        COLUMNS + " WHERE DATE(event_time) = '2019-11-15' AND event_type = 'purchase'"
    ),
    "Gold pg_monthly_profit": "SELECT * FROM `${project}.${gold}.pg_monthly_profit`",
}
SERVING_FILES = ["01_pipeline_health.sql", "02_data_freshness.sql", "03_eda_order_items.sql"]


def dry_run_bytes(client: bigquery.Client, sql: str) -> int:
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    return client.query(sql, job_config=job_config).total_bytes_processed


def report(client: bigquery.Client, cfg: config.Settings) -> str:
    """Markdown table: query name and the megabytes it would scan."""
    values = cfg.model_dump() | {"gold": os.environ.get("BQ_GOLD", "stylehub_gold")}
    sqls = {name: Template(sql).substitute(values) for name, sql in QUERIES.items()}
    for name in SERVING_FILES:
        sqls[f"dashboard {name}"] = bq.render_sql(config.SQL_DIR / "serving" / name, cfg)
    lines = ["| Query | MB scanned |", "|---|---:|"]
    lines += [f"| {name} | {dry_run_bytes(client, sql) / 1e6:,.1f} |" for name, sql in sqls.items()]
    return "\n".join(lines)


if __name__ == "__main__":
    settings = config.settings()
    print(report(config.bq_client(settings), settings))
