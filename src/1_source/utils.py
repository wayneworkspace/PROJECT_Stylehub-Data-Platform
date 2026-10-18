"""Shared helpers: data date checks and run ids."""

import uuid
from contextlib import suppress
from datetime import UTC, date, datetime


def new_id() -> str:
    """Time-sortable id: UTC timestamp plus 6 random hex characters."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def valid_date(value: str) -> str:
    """Return value if it is a real YYYY-MM-DD date, else raise."""
    with suppress(ValueError):
        if date.fromisoformat(value).isoformat() == value:
            return value
    raise ValueError(f"not a date in the form YYYY-MM-DD: {value!r}")
