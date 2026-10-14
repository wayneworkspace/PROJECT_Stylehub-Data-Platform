"""Retry a call that fails for a short time: the network drops, BigQuery or GCS is busy.

Only short-lived errors are retried. A wrong password, a missing table or bad SQL fails at once,
because waiting would not help. Each wait is twice as long as the one before (backoff).

Usage:
    rows = call_with_retry(lambda: client.query(sql).result())

Pass a function that starts the whole job again, for example one that creates a NEW query job.
Calling `.result()` on a job that already failed only gives the same error.
"""

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

import requests
from google.api_core import exceptions

log = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_ERRORS = (
    exceptions.BadGateway,
    exceptions.DeadlineExceeded,
    exceptions.GatewayTimeout,
    exceptions.InternalServerError,
    exceptions.ServiceUnavailable,
    exceptions.TooManyRequests,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)
# BigQuery sometimes reports a short problem as a plain error with one of these reasons.
TRANSIENT_REASONS = {"backendError", "internalError", "rateLimitExceeded"}


def is_transient(error: Exception) -> bool:
    """True when waiting and trying again can help."""
    if isinstance(error, TRANSIENT_ERRORS):
        return True
    details = getattr(error, "errors", None) or []
    reasons = {d.get("reason") for d in details if isinstance(d, dict)}
    return bool(reasons & TRANSIENT_REASONS)


def call_with_retry(
    func: Callable[[], T],
    attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call func(). On a short-lived error wait 2s, 4s, 8s ... (at most max_delay), then retry.

    After `attempts` tries the last error is raised. Other errors are raised at once.
    """
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as error:
            if attempt == attempts or not is_transient(error):
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            delay += random.uniform(0, delay / 4)  # jitter: many tasks do not retry together
            log.warning(
                "%s on try %d of %d, waiting %.1fs", type(error).__name__, attempt, attempts, delay
            )
            sleep(delay)
    raise AssertionError("unreachable")  # the loop always returns or raises
