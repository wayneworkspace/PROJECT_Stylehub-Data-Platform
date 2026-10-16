# DevOps

This page explains the DevOps parts of the repo and what to add next.

## What is in place

| Part | Files | What it does |
|---|---|---|
| Docker image | `deploy/pipeline/Dockerfile`, `.dockerignore` | Runs the pipeline in a clean environment. Python 3.12 and uv are pinned. It installs packages from `uv.lock` and does not run as root. Secrets are never copied in. |
| One compose file (profiles `pipeline`, `airflow`) | `docker-compose.yaml` | The Airflow image holds the code (nothing is mounted from your folder), so the laptop runs what the VM runs. |
| One Python version | `.python-version`, `pyproject.toml`, CI, both Dockerfiles | 3.12 everywhere. |
| Pre-commit | `.pre-commit-config.yaml` | Runs ruff (lint and format), gitleaks and file checks before each commit. |
| CI | `.github/workflows/ci.yaml` | Runs the same checks on each push to `main` and on pull requests: types, tests with a coverage limit, `dbt parse`, SQL lint, package scan, Docker build and image scan. Actions are pinned to commit ids. |
| CD | `.github/workflows/cd.yaml`, `docs/ops/CD.md` | After CI passes on a push to `main`, pushes the pipeline image and the Airflow image that CI tested (it does not build again). One tag, the commit id. The VM pulls them. No SSH into the VM. |
| Update bot | `.github/dependabot.yml` | Opens a pull request when an Action, a Docker tag or a Python package has a new version. |
| Locked packages | `uv.lock` | Keeps local, Docker and CI runs on the same package versions. |
| Logs and run history | `src/stylehub/orchestration/run_daily.py`, `src/stylehub/orchestration/runs.py`, `src/stylehub/sql/ops/` | Logs each step and saves one row per step in `stylehub_ops.pipeline_runs`. |
| Failure alerts | `src/stylehub/orchestration/alerts.py`, `deploy/airflow/dags/stylehub_daily.py` | By hand, `run_daily` sends a Discord message when a step fails. Under Airflow the DAG sends ONE message when a task fails for good, also when the task was killed. Off when `ALERT_WEBHOOK_URL` is empty. |
| Cost limit | `BQ_MAX_BYTES_BILLED`, `dbt/profiles.yml` | BigQuery refuses a query that would bill more than 50 GB (changeable). |
| VM jobs | `deploy/`, `docs/ops/DEPLOY_VM.md` | A run script. The systemd timers were removed; Airflow schedules the pipeline. |

## CI jobs

| Job | What it checks |
|---|---|
| Pre-commit checks | ruff lint, ruff format check, gitleaks, YAML files, large files, private keys, trailing spaces. |
| Types, tests, dbt, SQL | mypy, unit tests (fails below the coverage limit in `pyproject.toml`), `dbt parse`, sqlfluff on the dbt models, `pip-audit` on the locked packages. |
| Docker image | The image builds, starts, runs as a user that is not root, the compose file is valid, Trivy finds no fixable HIGH or CRITICAL problem, and an SBOM is saved. On `main` the tested image is kept for CD. |

CI does not call Google Cloud. It has no keys, so the BigQuery and GCS steps are not tested there. `dbt parse` and sqlfluff check that the models are valid dbt and BigQuery-style SQL. The models run on BigQuery only in `dbt-ci.yaml`, which needs the repository variable `WIF_CI_SERVICE_ACCOUNT`; until it is set, that workflow shows a yellow warning ("dbt build did not run") so the gap is visible.

Strictness: `mypy` has `disallow_untyped_defs` on and skips only the libraries without type hints (`[[tool.mypy.overrides]]` in `pyproject.toml`). Ruff also checks naive datetimes (`DTZ`), `os.path` (`PTH`), `RUF` and `C4`. sqlfluff forbids subqueries (rule ST05); `layout.cte_newline`, `layout.select_targets`, `structure.using` and `layout.indent` stay off on purpose (the models use another layout).

Secrets for dbt: `run_dbt.py` removes every variable whose NAME looks like a secret (`SECRET`, `PASSWORD`, `TOKEN`, `WEBHOOK`, `FERNET`, or starting with `AIRFLOW`) before it starts dbt.

## Images and versions

- CD pushes only the commit id as a tag. There is no `latest`. The VM names the exact tag or digest (`run_on_vm.sh` refuses `:latest`). To roll back, set `STYLEHUB_IMAGE` to an older commit id.
- The image CI tests is the image CD pushes. CI keeps it as a build artifact for one day, so CD must run within a day of CI. The artifact is about the size of the image; check your GitHub storage quota.
- To freeze the base images to one exact build, add `@sha256:<digest>` to the `FROM` lines (the command is in the Dockerfile comment). Dependabot then proposes new digests.

## Next steps

| Step | Why |
|---|---|
| Run it on a real VM | The files in `deploy/` have not run on GCP yet. Follow [DEPLOY_VM.md](DEPLOY_VM.md) and fix what breaks. |
| Retries and a "did not run" alert | Today a failed step is reported, but a timer that never fires is not. Add a dead-man check, for example a daily message that must arrive. |
| Replace key files | Done for the VM script and CD (attached service account, Workload Identity Federation). On your laptop use `gcloud auth application-default login` and leave `GOOGLE_APPLICATION_CREDENTIALS` out of `secrets/.env`; use a key file only for Airflow in Docker on a laptop. |
| Airflow 3 | Done in the files (3.3.2). Build the image, pin it by digest and run one DAG run on a VM. |
| Terraform | Done in `infra/terraform/` (not run yet). Follow [TERRAFORM.md](TERRAFORM.md): `fmt`, `validate`, import what exists, `plan`, `apply`. |
