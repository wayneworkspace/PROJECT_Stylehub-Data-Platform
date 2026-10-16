from unittest.mock import MagicMock

from google.api_core.exceptions import NotFound

from stylehub.bronze import copy_events


def run_with(monkeypatch, fail_in):
    """Run the copy. A copy job fails with NotFound in the regions listed in `fail_in`."""
    asked = []

    def copy_table(source, target, job_config, location):
        asked.append(location)
        job = MagicMock()
        job.result.side_effect = NotFound("no job") if location in fail_in else None
        return job

    client = MagicMock()
    client.get_dataset.return_value.location = "US"
    client.copy_table.side_effect = copy_table
    client.get_table.return_value.num_rows = 42
    monkeypatch.setattr(copy_events.bigquery, "Client", lambda project: client)
    return copy_events.copy_events(), asked


def test_copy_uses_the_target_region_first(monkeypatch):
    rows, asked = run_with(monkeypatch, fail_in=[])
    assert rows == 42
    assert asked == ["asia-southeast1"]


def test_copy_tries_the_source_region_when_the_first_fails(monkeypatch):
    rows, asked = run_with(monkeypatch, fail_in=["asia-southeast1"])
    assert rows == 42
    assert asked == ["asia-southeast1", "US"]


def test_copy_fails_with_an_error_when_no_region_works(monkeypatch):
    import pytest

    with pytest.raises(RuntimeError, match="either region"):
        run_with(monkeypatch, fail_in=["asia-southeast1", "US"])
