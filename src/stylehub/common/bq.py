"""Small BigQuery helpers that more than one step needs."""

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from stylehub.common.config import Settings, resolve
from stylehub.common.retry import call_with_retry


def query_config(cfg: Settings | None = None, **options: object) -> bigquery.QueryJobConfig:
    """A query config with the cost limit (BQ_MAX_BYTES_BILLED). Pass dry_run=True and so on."""
    return bigquery.QueryJobConfig(maximum_bytes_billed=resolve(cfg).max_bytes_billed, **options)


def table_exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        call_with_retry(lambda: client.get_table(table_id))
    except NotFound:
        return False
    return True
