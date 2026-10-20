"""Small BigQuery helpers shared by several pipeline steps."""

from importlib import import_module
from pathlib import Path
from string import Template

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")


def query_config(cfg: config.Settings) -> bigquery.QueryJobConfig:
    """Query config that caps billed bytes at BQ_MAX_BYTES_BILLED."""
    return bigquery.QueryJobConfig(maximum_bytes_billed=cfg.max_bytes_billed)


def table_exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        retry.call_with_retry(lambda: client.get_table(table_id))
    except NotFound:
        return False
    return True


def newest_before(table_id: str, column: str, data_date: str, cfg: config.Settings):
    """Newest column value in a Bronze table before data_date; None if no table.

    Partitions of data_date and later are left out, so a rerun reads the same window.
    """
    client = config.bq_client(cfg)
    if not table_exists(client, table_id):
        return None
    sql = f"SELECT MAX({column}) FROM `{table_id}` WHERE _PARTITIONDATE < DATE '{data_date}'"  # noqa: S608
    rows = retry.call_with_retry(lambda: list(client.query(sql, job_config=query_config(cfg))))
    return rows[0][0]


def render_sql(path: Path, cfg: config.Settings) -> str:
    """Read a SQL file and fill its ${placeholders} from settings."""
    return Template(path.read_text(encoding="utf-8")).substitute(cfg.model_dump())
