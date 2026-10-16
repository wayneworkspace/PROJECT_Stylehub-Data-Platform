"""Retry a call that fails for a short time: the network drops, BigQuery or GCS is busy.

Only short-lived errors are retried. A wrong password, a missing table or bad SQL fails at once,
because waiting would not help. Each wait is twice as long as the one before (backoff, with a
little random time so many tasks do not retry together).
The loop itself is google.api_core.retry.Retry. This file only says WHICH errors are short-lived.

Usage:
    rows = call_with_retry(lambda: client.query(sql).result())

Pass a function that starts the whole job again, for example one that creates a NEW query job.
Calling `.result()` on a job that already failed only gives the same error.
"""

import logging
from collections.abc import Callable

import requests
from google.api_core import exceptions
from google.api_core.retry import Retry
from google.auth import exceptions as auth_exceptions

log = logging.getLogger(__name__)

TRANSIENT_ERRORS = (
    ConnectionError,  # the built-in one: reset, aborted, refused
    TimeoutError,
    auth_exceptions.TransportError,
    exceptions.Aborted,
    exceptions.BadGateway,
    exceptions.DeadlineExceeded,
    exceptions.GatewayTimeout,
    exceptions.InternalServerError,
    exceptions.ServiceUnavailable,
    exceptions.TooManyRequests,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)
# BigQuery sometimes reports a short problem as a plain error with one of these reasons.
TRANSIENT_REASONS = {"backendError", "internalError", "rateLimitExceeded"}


def is_transient(error: BaseException) -> bool:
    """True when waiting and trying again can help."""
    if isinstance(error, TRANSIENT_ERRORS):
        return True
    details = getattr(error, "errors", None) or []
    reasons = {d.get("reason") for d in details if isinstance(d, dict)}
    return bool(reasons & TRANSIENT_REASONS)


def call_with_retry[T](func: Callable[[], T], timeout: float = 1800.0) -> T:
    """Call func(). On a short-lived error wait 2s, 4s, 8s ... (at most 60s) and try again.

    It gives up when `timeout` seconds have passed since the first try (a long job counts too)
    and raises the last error. Other errors are raised at once.
    """
    retry = Retry(
        predicate=is_transient,
        initial=2.0,
        maximum=60.0,
        multiplier=2.0,
        timeout=timeout,
        on_error=lambda error: log.warning("%s, trying again", type(error).__name__),
    )
    try:
        return retry(func)()
    except exceptions.RetryError as exc:
        raise (exc.cause or exc) from None
