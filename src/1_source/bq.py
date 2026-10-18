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


def render_sql(path: Path, cfg: config.Settings) -> str:
    """Read a SQL file and fill its ${placeholders} from settings."""
    return Template(path.read_text(encoding="utf-8")).substitute(cfg.model_dump())
