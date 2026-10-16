import argparse

import pytest

from stylehub.common.dates import date_arg, valid_date


def test_a_real_date_is_returned_as_it_is():
    assert valid_date("2026-10-01") == "2026-10-01"


@pytest.mark.parametrize(
    "value", ["2026-13-01", "2026-02-30", "01/10/2026", "20261001", "2026-10-1", "", "tomorrow"]
)
def test_a_wrong_date_is_refused(value):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        valid_date(value)


def test_argparse_gets_a_clear_error():
    assert date_arg("2026-10-01") == "2026-10-01"
    with pytest.raises(argparse.ArgumentTypeError, match="YYYY-MM-DD"):
        date_arg("2026-10-32")
