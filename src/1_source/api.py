"""StyleHub REST API: a JWT from the API key, and one page of an endpoint, with retries."""

from importlib import import_module

import requests

config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")

TIMEOUT_SECONDS = 60
PAGE_SIZE = 10_000  # the API maximum; a full page is about 4 MB of JSON


def get_json(session: requests.Session, url: str, params: dict) -> dict:
    """GET one URL; 429, 5xx and timeouts are retried, 400 and 401 fail at once."""

    def call() -> dict:
        response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    return retry.call_with_retry(call)


def open_session(cfg: config.Settings) -> requests.Session:
    """Session with a Bearer JWT, from POST /auth/token with the API key."""
    if cfg.stylehub_api_key is None:
        raise RuntimeError("STYLEHUB_API_KEY is not set in secrets/.env")
    session = requests.Session()

    def token() -> str:
        key = cfg.stylehub_api_key.get_secret_value()
        response = session.post(
            f"{cfg.stylehub_api_url}/auth/token", json={"api_key": key}, timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()["access_token"]

    session.headers["Authorization"] = f"Bearer {retry.call_with_retry(token)}"
    return session
