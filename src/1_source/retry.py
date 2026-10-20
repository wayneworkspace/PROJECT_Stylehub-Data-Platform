"""Retry short-lived GCP and network errors with exponential backoff."""

from collections.abc import Callable
from importlib import import_module

import requests
import sqlalchemy
from google.api_core import exceptions
from google.api_core.retry import Retry
from google.auth import exceptions as auth_exceptions

get_logger = import_module("src.0_utils.logger").get_logger

log = get_logger(__name__)

TRANSIENT_ERRORS = (
    ConnectionError,  # built-in: connection reset, aborted or refused
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
# BigQuery error reasons that also mean a short-lived problem.
TRANSIENT_REASONS = {"backendError", "internalError", "rateLimitExceeded"}
# Postgres network errors worth retrying; a wrong password is not.
PG_TRANSIENT_TEXT = ("timeout", "could not connect", "server closed", "connection reset")


def is_transient(error: BaseException) -> bool:
    """True when waiting and trying again can help."""
    if isinstance(error, TRANSIENT_ERRORS):
        return True
    if isinstance(error, requests.HTTPError) and error.response is not None:
        # 429 rate limit and 5xx pass; 400 and 401 are our mistake and never do.
        return error.response.status_code == 429 or error.response.status_code >= 500
    if isinstance(error, sqlalchemy.exc.OperationalError):
        return any(text in str(error).lower() for text in PG_TRANSIENT_TEXT)
    details = getattr(error, "errors", None) or []
    reasons = {d.get("reason") for d in details if isinstance(d, dict)}
    return bool(reasons & TRANSIENT_REASONS)


def call_with_retry[T](func: Callable[[], T]) -> T:
    """Call func, retrying short-lived errors for up to 30 minutes."""
    retry = Retry(
        predicate=is_transient,
        initial=2.0,
        maximum=60.0,
        multiplier=2.0,
        timeout=1800.0,
        on_error=lambda error: log.warning("%s, trying again", type(error).__name__),
    )
    try:
        return retry(func)()
    except exceptions.RetryError as exc:
        raise (exc.cause or exc) from None
