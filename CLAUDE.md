# CLAUDE.md — rules for AI when writing code in this repo

## Project
StyleHub Data Platform on GCP, built following a 5-session curriculum.
Source (course CSV tables in BigQuery; Postgres and API are optional) → Raw Zone (GCS) → Bronze → Silver (fact/dim) → Gold (BigQuery).
Curriculum stack: Python, SQL, GCS, BigQuery, Airbyte. dbt (`dbt/`) and Airflow (`deploy/airflow/`) are added on top.
Spark is a later extension: do not add it unless asked (see `docs/design/EXTENDING.md`).

## How to work (these rules come first)
Rules to avoid common AI coding mistakes. They favor caution over speed. For a trivial task, use judgment.

### 1. Think before coding
- State your assumptions. If you are unsure, ask.
- If a request has more than one reading, show the options. Do not pick one silently.
- If a simpler way exists, say so and push back when it is right to.
- If something is unclear, stop, name what is unclear and ask.

### 2. Simplicity first
- Write the minimum code that solves the problem. Nothing speculative.
- No features beyond the request. No abstraction for code used once.
- No "flexibility" or settings that nobody asked for.
- No error handling for cases that cannot happen. (Best-effort recording and alerts are the exception: they must not crash the pipeline.)
- If 200 lines could be 50, rewrite it. Ask: "Would a senior engineer call this overcomplicated?"
- Keep code readable. Prefer clear over clever. One file, one job. Short functions with names that say what they do.

### 3. Surgical changes
- Touch only what you must. Every changed line must trace to the request.
- Do not "improve" nearby code, comments or formatting. Do not refactor what is not broken.
- Match the existing style, even if you would do it differently.
- Remove imports, variables and functions that YOUR change made unused. If you see other dead code, mention it. Do not delete it.

### 4. Goal-driven execution
- Turn the task into a check you can run: "fix the bug" means write a test that fails, then make it pass. "Refactor" means tests pass before and after.
- For a task with several steps, write a short plan, each step with how you will verify it:
  1. Step -> verify: check
  2. Step -> verify: check
- "Make it work" is not a goal. Define success first, then loop until the check passes.

These rules are working if diffs are smaller, there are fewer rewrites, and questions come before the work, not after a mistake.

## How changes are delivered
- Work directly in the local folder `C:\Users\ADMIN\OneDrive\Desktop\End-to-End\PROJECT_Stylehub-Data-Platform`.
- No pull requests and no PR descriptions. Do not create a branch just to open a PR.
- Do not commit or push unless the owner asks. When asked, use Conventional Commits.
- Keep each change small and say how to check it.

## Repo conventions
- Organize Python by stage of the data flow, in `src/python/`: `ingestion/` (source to Raw Zone: `csv_tables.py` is the real flow; `ingestion/optional/` holds `database.py`, `api.py` and the `sources/` clients, which `run_daily` does not call), `storage/` (the daily Bronze steps; `storage/setup/` holds the scripts you run once by hand: `setup_gcp`, `load_csv`), `transform/` (dbt for Silver and Gold, SQL for Bronze), `orchestration/` (run order, logs, alerts), `common/` (settings). Serving is the Gold tables in BigQuery; add a `serving/` folder only when code is needed.
- Bronze and ops SQL live in `src/sql/{bronze,ops}`. Silver and Gold are dbt models in `dbt/models/`, laid out like dbt Labs: `staging/stylehub/` (`stg_stylehub__*`, the only place that calls `source()`), `intermediate/` (`int_*`), `marts/core/` (`dim_`, `fact_`, Silver dataset) and `marts/reporting/` (Gold dataset). Tags, materialization and dataset are set per folder in `dbt_project.yml`, not in each model. YAML files are named `_<folder>__models.yaml` and `_<source>__sources.yaml`. Python tests live in `src/tests/`, in one folder per stage (the same names as `src/python/`). The VM script lives in `deploy/pipeline/`.
- Follow PEP 8: 4 spaces, lines up to 100 characters, `snake_case` for functions and variables, `CapWords` for classes, imports sorted (ruff checks this). Every module starts with a docstring that says what it does and how to run it.
- Docs live in `docs/`: `design/` says why, `ops/` says how to run and ship it, `html/` and `assets/` hold pages and icons. Link pages with relative paths; a test checks the links.
- Commit using Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
- Name YAML files with the `.yaml` extension, never `.yml` (for example `ci.yaml`, `docker-compose.yaml`, Airbyte `values.yaml`). The only exceptions are `dbt/dbt_project.yml` and `dbt/profiles.yml`: dbt refuses other names for these two.

## Contract between layers (do not break, so extending never means rewriting)
- Every step runs on its own as a CLI with `--date` and is safe to re-run.
- Dataset names and the grain of each table are the contract. If a grain changes, update `docs/design/ARCHITECTURE.md`.
- Business logic lives in SQL files, not in Python code.
- Configuration is read only from `src/python/common/config.py` (environment variables), not scattered constants. The settings file is `secrets/.env` (copy `.env.example` there). Never read `.env` anywhere else.

## Ingestion
- Ingestion has ONE job: extract and write raw data. No transforming, no cleaning.
- The Raw Zone is append-only, never overwritten: `raw/stylehub/<table>/date=<YYYY-MM-DD>/batch_id=<id>/<table>.parquet`.
- Every raw file carries 3 metadata columns: `_ingested_at`, `_source`, `_batch_id`.
- Re-runs must be safe: same input, same number of distinct ids.

## SQL
- Write with CTEs. No subqueries.
- Number files by dependency order (`01_`, `02_`). Use `${project}`, `${bronze}`, `${silver}`, `${gold}`.
- Bronze: one snapshot per day. A re-run of the same day replaces that day's batch (no doubling); different days are kept. Large Silver facts (`fact_events`) are incremental. Silver: one latest row per id, cast types correctly, state the grain at the top of the file.
- Gold: holds business rules (for example, exclude `Cancelled` orders). When a rule changes, edit Gold and leave Silver alone.
- Every Silver table has a grain test (`unique` + `not_null`) in `dbt/models/staging/stylehub/_stylehub__models.yaml` and `dbt/models/marts/core/_core__models.yaml`. Gold has a test (`dbt/tests/gold_matches_silver.sql`) that reconciles its totals with Silver.
- Large tables (events) must have `PARTITION BY` and `CLUSTER BY`; record the reasoning and measurements in `docs/design/DECISIONS.md`.

## Security
- Never commit: `secrets/`, `.env`, GCP key JSON, HMAC keys, database passwords, raw CSV data.
- Restrict the Airbyte VM firewall to your own IP, never `0.0.0.0/0`. Stop the VM when not in use.
- The StyleHub dataset belongs to the course: publish only your own rebuilt code, not the instructor's materials or sample code.

## DevOps
- Docker, CI and pre-commit are in place (`docs/ops/DEVOPS.md`). Do not add other tools unless asked.
- Install packages with `uv` and keep `uv.lock` in sync (`uv lock` after you change `pyproject.toml`).
- Everything that runs lives in `deploy/`, one folder per part: `deploy/pipeline/` (Dockerfile, VM script) and `deploy/airflow/` (DAG, Dockerfile, README). Add new parts the same way. Sample data for local tests is not deployed: it lives in `dev/postgres/`. There is ONE `docker-compose.yaml` at the root, split by profile (`dev`, `pipeline`, `airflow`). Do not add another compose file.
- The Docker image must never contain secrets. Keep `.dockerignore` strict; pass secrets at run time (env vars or a read-only mount).
- Integration tests need Postgres: `docker compose up -d postgres`, then `uv run pytest -m integration`. If you change `dev/postgres/init/01_seed.sql`, update `src/tests/ingestion/optional/test_ingestion_integration.py` too.
- Airflow DAG (`deploy/airflow/dags/stylehub_daily.py`): `ExternalPythonOperator` for Python steps (ingest, bronze), `BashOperator` + CLI for dbt steps (silver, gold), `EmptyOperator` for `start` and `end`. Do not use `PythonOperator`: Airflow's pinned libraries clash with the pipeline's.
- Every call to BigQuery or GCS that can fail for a short time goes through `call_with_retry` (`src/python/common/retry.py`). Pass a function that starts the whole job again.
- Every pipeline step must go through `run_step` in `src/python/orchestration/run_daily.py`, so it is logged, recorded in `pipeline_runs` and alerted. Recording and alerts must never crash the pipeline.
- `ALERT_WEBHOOK_URL` and service-account keys are secrets: never log or commit them. Keep one service account per job (see `docs/ops/DEPLOY_VM.md`).
- CI actions and pre-commit hooks are pinned to versions. Check the real latest tag before you bump one.

## Before saying it is done
- `uv run ruff check .` and `uv run pytest` must pass. There is no Makefile: use these `uv run` commands.
- Run `uvx pre-commit run --all-files`.
- Update the README/docs when behavior changes.
- Read your own diff (`git diff`). Each changed line must trace to the request (rule 3).
