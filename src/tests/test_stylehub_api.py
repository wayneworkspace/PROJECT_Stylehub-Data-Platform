import pytest
import requests

from sources import stylehub_api
from sources.stylehub_api import ApiError, fetch_rows, get_json


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = text

    def json(self):
        return self._body


class FakeApi:
    """Answers with the given responses, in order. An exception in the list is raised."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []  # one entry per request: (url, params, headers)

    def __call__(self, url, params, headers, timeout):
        self.calls.append((url, dict(params), dict(headers)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture(autouse=True)
def api_settings(monkeypatch):
    monkeypatch.setenv("API_URL", "https://example.test/functions/v1/")
    monkeypatch.setenv("API_KEY", "super-secret-key")
    monkeypatch.delenv("API_KEY_HEADER", raising=False)


@pytest.fixture
def waits():
    """Replace sleep, so tests do not wait. Remember how long we would have waited."""
    return []


def page(rows, has_more):
    return FakeResponse(200, {"data": rows, "has_more": has_more})


def test_fetch_rows_reads_pages_until_has_more_is_false(waits):
    api = FakeApi(page([{"id": 1}, {"id": 2}], True), page([{"id": 3}], False))
    rows = fetch_rows("stylehub-users", {"created_from": "2026-10-01"}, get=api, sleep=waits.append)
    assert [row["id"] for row in rows] == [1, 2, 3]
    assert [call[1]["page"] for call in api.calls] == [1, 2]
    assert api.calls[0][0] == "https://example.test/functions/v1/stylehub-users"
    assert api.calls[0][1]["created_from"] == "2026-10-01"


def test_the_key_is_sent_in_the_header(waits):
    api = FakeApi(page([], False))
    fetch_rows("x", {}, get=api, sleep=waits.append)
    assert api.calls[0][2] == {"x-api-key": "super-secret-key"}


def test_the_header_name_can_be_changed(monkeypatch, waits):
    monkeypatch.setenv("API_KEY_HEADER", "apikey")
    api = FakeApi(page([], False))
    fetch_rows("x", {}, get=api, sleep=waits.append)
    assert api.calls[0][2] == {"apikey": "super-secret-key"}


def test_a_missing_key_stops_before_any_request(monkeypatch, waits):
    monkeypatch.delenv("API_KEY")
    api = FakeApi()
    with pytest.raises(ApiError, match="API_KEY"):
        fetch_rows("x", {}, get=api, sleep=waits.append)
    assert api.calls == []


def test_a_server_error_is_retried_and_the_wait_doubles(waits):
    api = FakeApi(FakeResponse(500), FakeResponse(503), page([{"id": 1}], False))
    rows = fetch_rows("x", {}, get=api, sleep=waits.append)
    assert rows == [{"id": 1}]
    assert len(api.calls) == 3
    assert waits == [1.0, 2.0]


def test_a_timeout_is_retried(waits):
    api = FakeApi(requests.Timeout(), page([{"id": 1}], False))
    assert fetch_rows("x", {}, get=api, sleep=waits.append) == [{"id": 1}]
    assert waits == [1.0]


def test_a_client_error_is_not_retried(waits):
    api = FakeApi(FakeResponse(401, text="bad key"))
    with pytest.raises(ApiError, match="HTTP 401"):
        get_json("https://example.test/x", {}, get=api, sleep=waits.append)
    assert len(api.calls) == 1
    assert waits == []


def test_it_gives_up_after_the_last_attempt(waits):
    api = FakeApi(*[FakeResponse(500) for _ in range(stylehub_api.MAX_ATTEMPTS)])
    with pytest.raises(ApiError, match="failed after"):
        get_json("https://example.test/x", {}, get=api, sleep=waits.append)
    assert len(api.calls) == stylehub_api.MAX_ATTEMPTS
    assert len(waits) == stylehub_api.MAX_ATTEMPTS - 1  # no wait after the last attempt


def test_the_error_message_does_not_contain_the_key(waits):
    api = FakeApi(*[FakeResponse(500) for _ in range(stylehub_api.MAX_ATTEMPTS)])
    with pytest.raises(ApiError) as error:
        get_json("https://example.test/x", {}, get=api, sleep=waits.append)
    assert "super-secret-key" not in str(error.value)


def test_a_has_more_that_never_ends_is_stopped(monkeypatch, waits):
    monkeypatch.setattr(stylehub_api, "MAX_PAGES", 3)
    api = FakeApi(*[page([{"id": n}], True) for n in range(5)])
    with pytest.raises(ApiError, match="still has_more"):
        fetch_rows("x", {}, get=api, sleep=waits.append)
    assert len(api.calls) == 3
