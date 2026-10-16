import re
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Conflict, NotFound

from stylehub.common.bq import load_job_once, table_exists
from stylehub.common.ids import new_id, new_job_id


def test_new_id_has_a_time_part_and_a_random_part():
    first, second = new_id(), new_id()
    assert re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{6}", first)
    assert first != second


def test_table_exists_is_true_when_bigquery_finds_it():
    assert table_exists(MagicMock(), "p.d.t") is True


def test_table_exists_is_false_when_the_table_is_missing():
    client = MagicMock()
    client.get_table.side_effect = NotFound("missing")
    assert table_exists(client, "p.d.t") is False


def test_new_job_id_has_the_prefix_and_is_different_each_time():
    first, second = new_job_id("bronze_orders"), new_job_id("bronze_orders")
    assert re.fullmatch(r"bronze_orders_[0-9a-f]{32}", first)
    assert first != second


def test_load_job_once_starts_the_job_and_waits_for_it():
    client, job = MagicMock(), MagicMock()
    assert load_job_once(client, lambda job_id: job, "j1") is job
    job.result.assert_called_once()
    client.get_job.assert_not_called()


def test_load_job_once_waits_for_the_existing_job_on_a_conflict():
    client, existing = MagicMock(), MagicMock(state="RUNNING", error_result=None)
    client.get_job.return_value = existing

    def start(job_id):
        raise Conflict("job exists")

    assert load_job_once(client, start, "j1", location="asia-southeast1") is existing
    client.get_job.assert_called_once_with("j1", location="asia-southeast1")
    existing.result.assert_called_once()


def test_load_job_once_starts_a_new_job_when_the_old_one_failed():
    # The first job id is taken by a job that FAILED. Waiting for it would give the same error,
    # so the load goes on under <id>_r1. Nothing was loaded by the failed job.
    client = MagicMock()
    client.get_job.return_value = MagicMock(state="DONE", error_result={"reason": "backendError"})
    new_job = MagicMock()
    started = []

    def start(job_id):
        started.append(job_id)
        if job_id == "j1":
            raise Conflict("job exists")
        return new_job

    assert load_job_once(client, start, "j1") is new_job
    assert started == ["j1", "j1_r1"]
    new_job.result.assert_called_once()


def test_load_job_once_gives_up_after_too_many_failed_jobs():
    client = MagicMock()
    client.get_job.return_value = MagicMock(state="DONE", error_result={"reason": "invalid"})

    def start(job_id):
        raise Conflict("job exists")

    with pytest.raises(RuntimeError, match="failed"):
        load_job_once(client, start, "j1")
    assert client.get_job.call_count == 5


def test_query_config_carries_the_cost_limit(monkeypatch):
    from stylehub.common.bq import query_config

    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "123456")
    config = query_config(dry_run=True)
    assert config.maximum_bytes_billed == 123456
    assert config.dry_run is True
