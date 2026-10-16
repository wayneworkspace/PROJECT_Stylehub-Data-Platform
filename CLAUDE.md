# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Project-specific rules (StyleHub)

The four guidelines above come first. The rules below add the conventions of this repo.

## Project
StyleHub Data Platform on GCP, built following a 5-session curriculum.
Source (course CSV tables in BigQuery) → Raw Zone (GCS) → Bronze → Silver (fact/dim) → Gold (BigQuery).
Curriculum stack: Python, SQL, GCS, BigQuery, Airbyte. dbt (`dbt/`), Airflow 3 (`deploy/airflow/`) and Terraform (`infra/terraform/`) are added on top.
Spark is a later extension: do not add it unless asked (see `docs/design/EXTENDING.md`).

## How changes are delivered
- Work directly in the local folder `C:\Users\ADMIN\OneDrive\Desktop\End-to-End\PROJECT_Stylehub-Data-Platform`.
- No pull requests and no PR descriptions. Do not create a branch just to open a PR.
- Do not commit or push unless the owner asks. When asked, use Conventional Commits.
- Keep each change small and say how to check it.

## Repo conventions
- Organize Python by stage of the data flow, in the one package `src/stylehub/`: `ingestion/` (source to Raw Zone: `csv_tables.py` is the flow; the old Postgres/API code was removed), `bronze/` (Raw Zone to Bronze, the daily steps), `setup/` (scripts you run once by hand: `setup_gcp`, `load_csv`), `transform/` (dbt for Silver and Gold, SQL for Bronze), `orchestration/` (run order, logs, alerts), `common/` (settings). Serving is not built yet: it is the Gold tables in BigQuery; add a `serving/` folder only when code is needed (see docs/design/ARCHITECTURE.md, Code map).
- Bronze and ops SQL live in `src/stylehub/sql/{bronze,ops}`. Silver and Gold are dbt models in `dbt/models/`, laid out like dbt Labs: `staging/stylehub/` (`stg_stylehub__*`, the only place that calls `source()`), `intermediate/` (`int_*`), `marts/core/` (`dim_`, `fact_`, Silver dataset) and `marts/reporting/` (Gold dataset). Tags, materialization and dataset are set per folder in `dbt_project.yml`, not in each model. YAML files are named `_<folder>__models.yaml` and `_<source>__sources.yaml`. Python tests live in `src/tests/`, in one folder per stage (the same names as `src/`). The VM script lives in `deploy/pipeline/`.
- Follow PEP 8: 4 spaces, lines up to 100 characters, `snake_case` for functions and variables, `CapWords` for classes, imports sorted (ruff checks this). Every module starts with a docstring that says what it does and how to run it.
- Docs live in `docs/`: `design/` says why, `ops/` says how to run and ship it, `html/` and `assets/` hold pages and icons. Link pages with relative paths; a test checks the links.
- Commit using Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
- Name YAML files with the `.yaml` extension, never `.yml` (for example `ci.yaml`, `docker-compose.yaml`, Airbyte `values.yaml`). The only exceptions are `dbt/dbt_project.yml` and `dbt/profiles.yml`: dbt refuses other names for these two.

## Contract between layers (do not break, so extending never means rewriting)
- Every step runs on its own as a CLI with `--date` and is safe to re-run.
- Dataset names and the grain of each table are the contract. If a grain changes, update `docs/design/ARCHITECTURE.md`.
- Business logic lives in SQL files, not in Python code.
- Configuration is read only from `src/stylehub/common/config.py` (environment variables), not scattered constants. The settings file is `secrets/.env` (copy `.env.example` there). Never read `.env` anywhere else.

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
- Docker, CI, pre-commit and Terraform (`infra/terraform/`, owner approved on 2026-10-16) are in place (`docs/ops/DEVOPS.md`). Do not add other tools unless asked.
- Install packages with `uv` and keep `uv.lock` in sync (`uv lock` after you change `pyproject.toml`).
- Everything that runs lives in `deploy/`, one folder per part: `deploy/pipeline/` (Dockerfile, VM script) and `deploy/airflow/` (DAG, Dockerfile, README). Add new parts the same way.  There is ONE `docker-compose.yaml` at the root, split by profile (`pipeline`, `airflow`). Do not add another compose file.
- The Docker image must never contain secrets. Keep `.dockerignore` strict; pass secrets at run time (env vars or a read-only mount).
- Quality gates: `ruff check`, `ruff format --check`, `mypy`, `pytest --cov` (80% minimum), `sqlfluff lint`, `dbt parse`. CI runs them all. Images are tagged with the commit id, never `latest`.
- Airflow 3 DAG (`deploy/airflow/dags/stylehub_daily.py`; imports from `airflow.sdk` and `airflow.providers.standard`, schedule is `CronDataIntervalTimetable` so `ds` is the day before the run): `ExternalPythonOperator` for Python steps (ingest, bronze), `BashOperator` + CLI for dbt steps (silver, gold), `EmptyOperator` for `start` and `end`. Do not use `PythonOperator`: Airflow's pinned libraries clash with the pipeline's.
- Every call to BigQuery or GCS that can fail for a short time goes through `call_with_retry` (`src/stylehub/common/retry.py`). Pass a function that starts the whole job again.
- Every pipeline step must go through `run_step` in `src/stylehub/orchestration/run_daily.py`, so it is logged, recorded in `pipeline_runs` and alerted. Recording and alerts must never crash the pipeline.
- `ALERT_WEBHOOK_URL` and service-account keys are secrets: never log or commit them. Keep one service account per job (see `docs/ops/DEPLOY_VM.md`).
- CI actions and pre-commit hooks are pinned to versions. Check the real latest tag before you bump one.

## Before saying it is done
- `uv run ruff check .`, `uv run mypy` and `uv run pytest` must pass. The Makefile only has `make clean` (removes caches and dbt build output): use the `uv run` commands for lint and tests.
- Run `uvx pre-commit run --all-files`.
- Update the README/docs when behavior changes.
- Read your own diff (`git diff`). Each changed line must trace to the request (rule 3).
