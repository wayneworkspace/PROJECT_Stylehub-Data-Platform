from google.api_core.exceptions import NotFound

from storage import copy_events


class FakeJob:
    def __init__(self, error):
        self.error = error

    def result(self):
        if self.error:
            raise self.error


class FakeClient:
    """Remember where the copy was asked. Fail in the regions listed in `fail_in`."""

    def __init__(self, fail_in):
        self.fail_in = fail_in
        self.asked = []

    def get_dataset(self, dataset_id):
        return type("Dataset", (), {"location": "US"})()

    def copy_table(self, source, target, job_config, location):
        self.asked.append(location)
        return FakeJob(NotFound("no job") if location in self.fail_in else None)

    def get_table(self, table_id):
        return type("Table", (), {"num_rows": 42})()


def run_with(monkeypatch, fail_in):
    client = FakeClient(fail_in)
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setenv("GCS_BUCKET", "b")
    monkeypatch.setattr(copy_events.bigquery, "Client", lambda project: client)
    return copy_events.copy_events(), client.asked


def test_copy_uses_the_target_region_first(monkeypatch):
    rows, asked = run_with(monkeypatch, fail_in=[])
    assert rows == 42
    assert asked == ["asia-southeast1"]


def test_copy_tries_the_source_region_when_the_first_fails(monkeypatch):
    rows, asked = run_with(monkeypatch, fail_in=["asia-southeast1"])
    assert rows == 42
    assert asked == ["asia-southeast1", "US"]
