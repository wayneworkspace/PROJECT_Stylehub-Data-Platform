"""Retry a call that fails for a short time: the network drops, BigQuery or GCS is busy.

Only short-lived errors are retried. A wrong password, a missing table or bad SQL fails at once,
because waiting would not help. Each wait is twice as long as the one before (backoff).
The loop itself comes from the tenacity library. This file only says WHICH errors are short-lived.

Usage:
    rows = call_with_retry(lambda: client.query(sql).result())

Pass a function that starts the whole job again, for example one that creates a NEW query job.
Calling `.result()` on a job that already failed only gives the same error.
"""

import logging
import time
from collections.abc import Callable

import requests
from google.api_core import exceptions
from google.auth import exceptions as auth_exceptions
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

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


def _log_retry(state: RetryCallState) -> None:
    if state.outcome is None or state.next_action is None:  # tenacity always sets both here
        return
    error = state.outcome.exception()
    log.warning(
        "%s on try %d, waiting %.1fs",
        type(error).__name__,
        state.attempt_number,
        state.next_action.sleep,
    )


def call_with_retry[T](
    func: Callable[[], T],
    attempts: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call func(). On a short-lived error wait 2s, 4s, 8s, 16s ... (at most max_delay), then retry.

    After `attempts` tries the last error is raised. Other errors are raised at once.
    A little random time is added to each wait, so many tasks do not retry together.
    """
    retrying = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=base_delay, max=max_delay, jitter=base_delay / 2),
        retry=retry_if_exception(is_transient),
        before_sleep=_log_retry,
        sleep=sleep,
        reraise=True,
    )
    return retrying(func)
