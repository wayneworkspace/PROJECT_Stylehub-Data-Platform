# DevOps

This page explains the DevOps parts of the repo and what to add next.

## What is in place

| Part | Files | What it does |
|---|---|---|
| Docker image | `Dockerfile`, `.dockerignore` | Runs the pipeline in a clean environment. It installs packages from `uv.lock` and does not run as root. Secrets are never copied in. |
| Local Postgres | `docker-compose.yml`, `docker/postgres/init/01_seed.sql` | Starts Postgres 16 with a small, fixed set of sample orders. The port is open to your own computer only. |
| Pre-commit | `.pre-commit-config.yaml` | Runs ruff, gitleaks and file checks before each commit. |
| CI | `.github/workflows/ci.yml` | Runs the same checks on each pull request, and also the tests and a Docker build. |
| Pull request template | `.github/pull_request_template.md` | Reminds you to run the checks and to keep secrets out. |
| Locked packages | `uv.lock` | Keeps local, Docker and CI runs on the same package versions. |

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
| Logging and a run history table | Plain `print` lines are hard to search. Log the step, the date, the row count and the time, and write one row per run to BigQuery. |
| Failure alerts | A failed step or check should send a message to Discord or email. |
| Run on a GCP VM | Practice Linux and networking. Use cron or a systemd timer, read logs with `journalctl`, and limit the firewall to your own IP. |
| One service account per job | Ingestion should write only to GCS. Transform should write only to BigQuery. |
| Push the image | Build in CI and push to Artifact Registry. Use Workload Identity Federation, not a key file. |
| Terraform | Describe the bucket, datasets, service accounts and VM as code. Do this after you have built them by hand once. |
