"""deploy/pipeline/run_on_vm.sh, run with a fake `docker` and a fake `gcloud` (no cloud needed)."""

import os
import shutil
import stat
import subprocess
import sys

import pytest

from stylehub.common.config import ROOT

SCRIPT = ROOT / "deploy" / "pipeline" / "run_on_vm.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="needs bash (Linux, macOS or WSL)",
)


@pytest.fixture
def vm(tmp_path):
    """A folder with a fake docker and gcloud that write what they were asked to a log file."""
    log = tmp_path / "calls.log"
    for name in ("docker", "gcloud"):
        fake = tmp_path / name
        fake.write_text(
            f'#!/bin/sh\necho "{name} $*" >> "{log}"\n'
            # Only `docker login --password-stdin` reads the pipe. If it did not, `gcloud | docker`
            # could die of SIGPIPE (exit 141) now and then and make this test flaky.
            f'[ "{name} $1" = "docker login" ] && cat > /dev/null\n'
            f'[ "{name}" = gcloud ] && echo fake-token\nexit 0\n'
        )
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env_file = tmp_path / "pipeline.env"
    env_file.write_text("GCP_PROJECT_ID=p\n")
    env = {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "STYLEHUB_ENV_FILE": str(env_file),
        "DATA_DATE": "2026-10-01",
        "HOME": str(tmp_path),
    }

    def run(*args, image=None):
        full_env = dict(env)
        if image:
            full_env["STYLEHUB_IMAGE"] = image
        result = subprocess.run(
            ["bash", str(SCRIPT), *args], env=full_env, capture_output=True, text=True
        )
        calls = log.read_text().splitlines() if log.exists() else []
        return result, calls

    return run


def test_it_needs_exactly_two_arguments(vm):
    result, calls = vm("ingest")
    assert result.returncode == 2 and calls == []


def test_a_local_image_runs_without_a_login_and_without_a_key_file(vm):
    result, calls = vm("ingest", "ingest")
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1 and calls[0].startswith("docker run --rm --env-file")
    assert "-v" not in calls[0] and "GOOGLE_APPLICATION_CREDENTIALS" not in calls[0]
    assert "--date 2026-10-01 --from-step ingest --to-step ingest" in calls[0]


@pytest.mark.parametrize("image", ["eu-docker.pkg.dev/p/r/img:latest", "eu-docker.pkg.dev/p/r/img"])
def test_an_image_without_a_version_is_refused(vm, image):
    result, calls = vm("ingest", "ingest", image=image)
    assert result.returncode == 2 and calls == []
    assert "version" in result.stderr or "tag" in result.stderr


def test_a_pinned_image_is_pulled_with_the_vm_token_then_run(vm):
    image = "eu-docker.pkg.dev/p/r/img:0123abc"
    result, calls = vm("bronze", "gold", image=image)
    assert result.returncode == 0, result.stderr
    # The token and the login run in one pipe, so their order in the log is not fixed.
    assert {c.split()[0] + " " + c.split()[1] for c in calls[:2]} == {"gcloud auth", "docker login"}
    assert any("oauth2accesstoken" in c for c in calls[:2])
    assert [c.split()[0:2] for c in calls[2:]] == [["docker", "pull"], ["docker", "run"]]
    assert "-v" not in calls[3]
    assert image in calls[3]


def test_a_digest_is_accepted(vm):
    result, _ = vm("ingest", "ingest", image="eu-docker.pkg.dev/p/r/img@sha256:" + "a" * 64)
    assert result.returncode == 0, result.stderr
