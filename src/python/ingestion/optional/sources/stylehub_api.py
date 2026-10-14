"""Client for the StyleHub REST API.

It does the three things every API client needs, and nothing else:
  1. Authentication: send the API key in a header.
  2. Paging: ask for page 1, 2, 3 ... until the answer says has_more is false.
  3. Retries: a server error (5xx), a timeout or a rate limit (429) is tried again, and the
     wait doubles each time. Other errors (400, 401, 404, ...) are our mistake, so we stop.

Settings come from the environment (call common.config.load_env() first):
  API_URL         base URL, for example https://<project>.supabase.co/functions/v1
  API_KEY         the key that the StyleHub API Reference gives you
  API_KEY_HEADER  header that carries the key (default x-api-key, check the API Reference)

Check against the StyleHub API Reference: the header name, the name of the list in the answer
(ROWS_KEY) and the first page number (FIRST_PAGE).
"""

import logging
import os
import time
from collections.abc import Callable

import requests

log = logging.getLogger(__name__)

DEFAULT_KEY_HEADER = "x-api-key"
ROWS_KEY = "data"  # the answer looks like {"data": [...], "has_more": true}
FIRST_PAGE = 1
MAX_PAGES = 10_000  # safety stop, so a broken has_more cannot loop forever
MAX_ATTEMPTS = 4
FIRST_WAIT_SECONDS = 1.0  # waits 1s, 2s, 4s between the attempts
REQUEST_TIMEOUT_SECONDS = 30
RETRY_STATUS = {429}  # plus every 5xx, see _should_retry


class ApiError(RuntimeError):
    """The API did not give us the data."""


def _should_retry(status_code: int) -> bool:
    return status_code >= 500 or status_code in RETRY_STATUS


def _headers() -> dict[str, str]:
    key = os.environ.get("API_KEY")
    if not key:
        raise ApiError("API_KEY is not set. Add it to secrets/.env (see .env.example).")
    return {os.environ.get("API_KEY_HEADER", DEFAULT_KEY_HEADER): key}


def get_json(
    url: str,
    params: dict[str, str | int],
    get: Callable = requests.get,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """GET one URL and return the JSON answer. Retry the errors that can go away on their own.

    `get` and `sleep` can be replaced in tests, so no test needs the network or real waiting.
    """
    headers = _headers()
    wait_seconds = FIRST_WAIT_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as exc:
            problem = type(exc).__name__
        else:
            if response.status_code < 400:
                return response.json()
            if not _should_retry(response.status_code):
                raise ApiError(f"HTTP {response.status_code} from {url}: {response.text[:200]}")
            problem = f"HTTP {response.status_code}"

        if attempt == MAX_ATTEMPTS:
            raise ApiError(f"{url} failed after {MAX_ATTEMPTS} attempts, last problem: {problem}")
        log.warning(
            "%s: %s, attempt %s of %s, waiting %ss",
            url, problem, attempt, MAX_ATTEMPTS, wait_seconds,
        )
        sleep(wait_seconds)
        wait_seconds *= 2
    raise AssertionError("unreachable")  # the loop always returns or raises


def fetch_rows(
    endpoint: str,
    params: dict[str, str | int],
    get: Callable = requests.get,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Read every page of one endpoint and return all rows."""
    url = f"{os.environ['API_URL'].rstrip('/')}/{endpoint}"
    rows: list[dict] = []
    page = FIRST_PAGE
    for _ in range(MAX_PAGES):
        answer = get_json(url, {**params, "page": page}, get=get, sleep=sleep)
        rows.extend(answer[ROWS_KEY])
        if not answer.get("has_more"):
            return rows
        page += 1
    raise ApiError(f"{url}: still has_more after {MAX_PAGES} pages")
