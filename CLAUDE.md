# CLAUDE.md — rules for AI when writing code in this repo

## Project
StyleHub Data Platform on GCP, built following a 5-session curriculum.
Source (Postgres + API) → Raw Zone (GCS) → Bronze → Silver (fact/dim) → Gold (BigQuery).
Only the curriculum stack is used for now: Python, SQL, GCS, BigQuery, Airbyte.
dbt, Airflow and Spark are later extensions: do not add them unless asked (see `docs/EXTENDING.md`).

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

## Repo conventions
- Organize folders by layer: `ingestion/`, `sql/{bronze,silver,gold,checks,ops}`, `pipeline/`.
- Commit using Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).

## Contract between layers (do not break, so extending never means rewriting)
- Every step runs on its own as a CLI with `--date` and is safe to re-run.
- Dataset names and the grain of each table are the contract. If a grain changes, update `docs/ARCHITECTURE.md`.
- Business logic lives in SQL files, not in Python code.
- Configuration is read only from `pipeline/config.py` (environment variables), not scattered constants.

## Ingestion
- Ingestion has ONE job: extract and write raw data. No transforming, no cleaning.
- The Raw Zone is append-only, never overwritten: `raw/stylehub/<table>/date=<YYYY-MM-DD>/batch_id=<id>/<table>.parquet`.
- Every raw file carries 3 metadata columns: `_ingested_at`, `_source`, `_batch_id`.
- Re-runs must be safe: same input, same number of distinct ids.

## SQL
- Write with CTEs. No subqueries.
- Number files by dependency order (`01_`, `02_`). Use `${project}`, `${bronze}`, `${silver}`, `${gold}`.
- Bronze: append rows only, keep every version. Silver: one latest row per id, cast types correctly, state the grain at the top of the file.
- Gold: holds business rules (for example, exclude `Cancelled` orders). When a rule changes, edit Gold and leave Silver alone.
- Every Silver table has a grain check in `sql/checks/`. Gold has a check that reconciles its totals with Silver.
- Large tables (events) must have `PARTITION BY` and `CLUSTER BY`; record the reasoning and measurements in `docs/DECISIONS.md`.

## Security
- Never commit: `secrets/`, `.env`, GCP key JSON, HMAC keys, database passwords, raw CSV data.
- Restrict the Airbyte VM firewall to your own IP, never `0.0.0.0/0`. Stop the VM when not in use.
- The StyleHub dataset belongs to the course: publish only your own rebuilt code, not the instructor's materials or sample code.

## DevOps
- Docker, CI and pre-commit are in place (`docs/DEVOPS.md`). Do not add other tools unless asked.
- Install packages with `uv` and keep `uv.lock` in sync (`uv lock` after you change `pyproject.toml`).
- The Docker image must never contain secrets. Keep `.dockerignore` strict; pass secrets at run time (env vars or a read-only mount).
- Integration tests need Postgres: `make up`, then `make test-integration`. If you change `docker/postgres/init/01_seed.sql`, update `tests/test_ingestion_integration.py` too.
- Every pipeline step must go through `run_step` in `pipeline/run_daily.py`, so it is logged, recorded in `pipeline_runs` and alerted. Recording and alerts must never crash the pipeline.
- `ALERT_WEBHOOK_URL` and service-account keys are secrets: never log or commit them. Keep one service account per job (see `docs/DEPLOY_VM.md`).
- CI actions and pre-commit hooks are pinned to versions. Check the real latest tag before you bump one.

## Before saying it is done
- `make lint` and `make test` must pass.
- Run `uvx pre-commit run --all-files`.
- Update the README/docs when behavior changes.
- Read your own diff (`git diff`). Each changed line must trace to the request (rule 3).
