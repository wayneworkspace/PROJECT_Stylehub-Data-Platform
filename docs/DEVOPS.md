# DevOps

This page explains the DevOps parts of the repo and what to add next.

## What is in place

| Part | Files | What it does |
|---|---|---|
| Docker image | `Dockerfile`, `.dockerignore` | Runs the pipeline in a clean environment. It installs packages from `uv.lock` and does not run as root. Secrets are never copied in. |
| Local Postgres | `docker-compose.yaml`, `docker/postgres/init/01_seed.sql` | Starts Postgres 16 with a small, fixed set of sample orders. The port is open to your own computer only. |
| Pre-commit | `.pre-commit-config.yaml` | Runs ruff, gitleaks and file checks before each commit. |
| CI | `.github/workflows/ci.yaml` | Runs the same checks on each push to `main`, and also the tests and a Docker build. |
| Locked packages | `uv.lock` | Keeps local, Docker and CI runs on the same package versions. |
| Logs and run history | `pipeline/run_daily.py`, `pipeline/runs.py`, `sql/ops/` | Logs each step and saves one row per step in `stylehub_ops.pipeline_runs`. |
| Failure alerts | `pipeline/alerts.py` | Sends a Discord message when a step fails. Off when `ALERT_WEBHOOK_URL` is empty. |
| VM jobs | `deploy/`, `docs/DEPLOY_VM.md` | A script and systemd timers. Two jobs, each with its own service account. |

## CI jobs

| Job | What it checks |
|---|---|
| Pre-commit checks | ruff, gitleaks, YAML files, large files, private keys, trailing spaces. |
| Lint and tests | ruff, unit tests, then integration tests against a Postgres service that holds the sample data. |
| Docker image | The image builds, starts, and runs as a user that is not root. |

CI does not call Google Cloud. It has no keys, so the BigQuery and GCS steps are not tested there.

## Sample data

`docker/postgres/init/01_seed.sql` is fixed on purpose, so tests can count on it. For the date 2026-10-01, the lookback window returns 24 orders and 46 order items. Order 100 tests a late update. Order 101 is too old and must stay out.

If you change this file, update `tests/test_ingestion_integration.py` too.

## Next steps

| Step | Why |
|---|---|
| Run it on a real VM | The files in `deploy/` have not run on GCP yet. Follow [DEPLOY_VM.md](DEPLOY_VM.md) and fix what breaks. |
| Retries and a "did not run" alert | Today a failed step is reported, but a timer that never fires is not. Add a dead-man check, for example a daily message that must arrive. |
| Replace key files | Use Workload Identity Federation or an attached service account, not JSON keys on disk. |
| Push the image | Build in CI and push to Artifact Registry. |
| Terraform | Describe the bucket, datasets, service accounts and VM as code. Do this after you have built them by hand once. |
