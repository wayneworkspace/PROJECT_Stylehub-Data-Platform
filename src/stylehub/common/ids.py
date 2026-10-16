"""One way to make an id that sorts by time: 20261001T030000-a1b2c3."""

import uuid
from datetime import UTC, datetime


def new_id() -> str:
    """The UTC time to the second, then 6 random characters so two ids never clash."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def new_job_id(prefix: str) -> str:
    """A BigQuery job id like bronze_orders_<random>. Make it once per load, keep it on retries."""
    return f"{prefix}_{uuid.uuid4().hex}"
