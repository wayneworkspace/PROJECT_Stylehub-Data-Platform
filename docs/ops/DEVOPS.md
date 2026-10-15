# DevOps

This page explains the DevOps parts of the repo and what to add next.

## What is in place

| Part | Files | What it does |
|---|---|---|
| Docker image | `deploy/pipeline/Dockerfile`, `.dockerignore` | Runs the pipeline in a clean environment. It installs packages from `uv.lock` and does not run as root. Secrets are never copied in. |
| One compose file (profiles `dev`, `pipeline`, `airflow`) and a local Postgres | `docker-compose.yaml`, `dev/postgres/init/01_seed.sql` | Starts Postgres 16 with a small, fixed set of sample orders. The port is open to your own computer only. |
| Pre-commit | `.pre-commit-config.yaml` | Runs ruff, gitleaks and file checks before each commit. |
| CI | `.github/workflows/ci.yaml` | Runs the same checks on each push to `main`, and also the tests and a Docker build. |
| CD | `.github/workflows/cd.yaml`, `docs/ops/CD.md` | After CI passes on `main`, builds the image and pushes it to Artifact Registry. The VM pulls it. No SSH into the VM. |
| Locked packages | `uv.lock` | Keeps local, Docker and CI runs on the same package versions. |
| Logs and run history | `src/python/orchestration/run_daily.py`, `src/python/orchestration/runs.py`, `src/sql/ops/` | Logs each step and saves one row per step in `stylehub_ops.pipeline_runs`. |
| Failure alerts | `src/python/orchestration/alerts.py` | Sends a Discord message when a step fails. Off when `ALERT_WEBHOOK_URL` is empty. |
| VM jobs | `deploy/`, `docs/ops/DEPLOY_VM.md` | A run script. The systemd timers were removed; Airflow schedules the pipeline. |

## CI jobs

| Job | What it checks |
|---|---|
| Pre-commit checks | ruff, gitleaks, YAML files, large files, private keys, trailing spaces. |
| Lint and tests | ruff, unit tests, then integration tests against a Postgres service that holds the sample data. |
| Docker image | The image builds, starts, and runs as a user that is not root. |

CI does not call Google Cloud. It has no keys, so the BigQuery and GCS steps are not tested there.

## Sample data

`dev/postgres/init/01_seed.sql` is fixed on purpose, so tests can count on it. For the date 2026-10-01, the lookback window returns 24 orders and 46 order items. Order 100 tests a late update. Order 101 is too old and must stay out.

If you change this file, update `src/tests/ingestion/optional/test_ingestion_integration.py` too.

## Next steps

| Step | Why |
|---|---|
| Run it on a real VM | The files in `deploy/` have not run on GCP yet. Follow [DEPLOY_VM.md](DEPLOY_VM.md) and fix what breaks. |
| Retries and a "did not run" alert | Today a failed step is reported, but a timer that never fires is not. Add a dead-man check, for example a daily message that must arrive. |
| Replace key files | Use Workload Identity Federation or an attached service account, not JSON keys on disk. |
| Terraform | Describe the bucket, datasets, service accounts and VM as code. Do this after you have built them by hand once. |
