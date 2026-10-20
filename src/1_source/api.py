"""StyleHub API: API key and one page of an endpoint, with retries."""

from importlib import import_module

import requests

config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")

TIMEOUT_SECONDS = 30
PAGE_SIZE = 1000  # the API maximum


def base_url(cfg: config.Settings) -> str:
    """API base URL; fails clearly when STYLEHUB_API_URL is missing."""
    if not cfg.stylehub_api_url:
        raise RuntimeError("STYLEHUB_API_URL is not set in secrets/.env")
    return cfg.stylehub_api_url.rstrip("/")


def get_json(session: requests.Session, url: str, params: dict) -> dict:
    """GET one URL; 429, 5xx and timeouts are retried, 400 and 401 fail at once."""

    def call() -> dict:
        response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    return retry.call_with_retry(call)


def open_session(cfg: config.Settings) -> requests.Session:
    """Session with the Bearer key: the one in .env, or a new one from the API."""
    session = requests.Session()
    if cfg.stylehub_api_key is not None:
        key = cfg.stylehub_api_key.get_secret_value()
    else:  # the key endpoint itself needs no key
        key = get_json(session, f"{base_url(cfg)}/stylehub-api-keys", {})["api_key"]
    session.headers["Authorization"] = f"Bearer {key}"
    return session
