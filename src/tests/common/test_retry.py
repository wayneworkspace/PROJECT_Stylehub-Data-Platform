"""The retry helper: short errors are retried, other errors are not."""

import pytest
from google.api_core import exceptions

from stylehub.common.retry import call_with_retry, is_transient


class Flaky:
    """Fails `failures` times with `error`, then returns "ok"."""

    def __init__(self, failures, error):
        self.failures, self.error, self.calls = failures, error, 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


def test_a_short_error_is_retried_until_it_works():
    func, waits = Flaky(2, exceptions.ServiceUnavailable("busy")), []
    assert call_with_retry(func, sleep=waits.append) == "ok"
    assert func.calls == 3
    assert len(waits) == 2


def test_waits_grow_each_time():
    func, waits = Flaky(3, exceptions.InternalServerError("oops")), []
    call_with_retry(func, base_delay=2.0, sleep=waits.append)
    assert 2 <= waits[0] < 3 and 4 <= waits[1] < 5 and 8 <= waits[2] < 10


def test_other_errors_fail_at_once():
    func = Flaky(5, exceptions.NotFound("no table"))
    with pytest.raises(exceptions.NotFound):
        call_with_retry(func, sleep=lambda s: None)
    assert func.calls == 1


def test_gives_up_after_the_last_try():
    func = Flaky(99, exceptions.ServiceUnavailable("still busy"))
    with pytest.raises(exceptions.ServiceUnavailable):
        call_with_retry(func, attempts=3, sleep=lambda s: None)
    assert func.calls == 3


@pytest.mark.parametrize(
    "error",
    [ConnectionResetError("reset"), TimeoutError("slow"), exceptions.Aborted("conflict")],
)
def test_network_resets_and_aborted_jobs_are_short_lived(error):
    assert is_transient(error)


def test_a_bigquery_reason_counts_as_short_lived():
    error = exceptions.Forbidden("slow down", errors=[{"reason": "rateLimitExceeded"}])
    assert is_transient(error)
    assert not is_transient(exceptions.Forbidden("no access", errors=[{"reason": "accessDenied"}]))
