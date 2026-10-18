"""Products API (dummyjson.com): one page of products, with retries."""

from importlib import import_module

import requests

retry = import_module("src.1_source.retry")

# Only the fields the pipeline keeps; the API returns id as well.
FIELDS = "title,category,brand,price,discountPercentage,rating,stock,availabilityStatus,meta"
TIMEOUT_SECONDS = 30


def get_page(session: requests.Session, base_url: str, skip: int, limit: int) -> dict:
    """GET /products for one page; HTTP 429 and 5xx are retried."""

    def call() -> dict:
        response = session.get(
            f"{base_url.rstrip('/')}/products",
            params={"skip": skip, "limit": limit, "select": FIELDS},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    return retry.call_with_retry(call)
