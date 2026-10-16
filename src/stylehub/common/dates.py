"""The data date is a plain string YYYY-MM-DD. Check it once, at the door of the pipeline.

A wrong date would otherwise travel into GCS paths and BigQuery before anything complains.
"""

import argparse
from datetime import date


def valid_date(value: str) -> str:
    """Return the value if it is a real date written as YYYY-MM-DD, else raise ValueError."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise ValueError(f"not a date in the form YYYY-MM-DD: {value!r}")
    return value


def date_arg(value: str) -> str:
    """The same check for argparse: add_argument("--date", type=date_arg)."""
    try:
        return valid_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
