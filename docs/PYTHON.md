# Python Commands

Environment, settings, one-off runs, tests and checks for the code in `src/`. Commands are `bash` (Git Bash) or PowerShell from the project folder; both work unless marked.

## 1. Environment

| Item | Value |
|---|---|
| Python | 3.13 (`.python-version`, `requires-python >=3.13,<3.14`) |
| Package manager | `uv`; lock file `uv.lock`; venv `.venv/` |
| Extras | `dev` (pytest, ruff, sqlfluff), `dbt`, `serving` (Streamlit) |
| Airflow image packages | `requirements.txt`, exported from `uv.lock` |
| Settings file | `secrets/.env` (template `.env.example`), loaded by `src/1_source/config.py` |
| GCP key | `GOOGLE_APPLICATION_CREDENTIALS=secrets/<key>.json`, path relative to the project folder |
| Postgres | `POSTGRES_URL` (read-only course account) |
| Module layout | `src/0_utils` (logger), `src/1_source` ... `src/5_serving`; no `__init__.py`; load with `import_module("src.2_ingestion.csv_tables")` |

```bash
uv sync --extra dev --extra dbt --extra serving     # install everything
uv add <package>                                    # add a dependency, then export:
uv export --frozen --no-hashes --no-dev --extra dbt --no-emit-project -o requirements.txt
```

## 2. Check settings and accounts

```bash
# Values the pipeline will use (no secrets printed)
uv run python -c "from importlib import import_module; c = import_module('src.1_source.config').settings(); print(c.model_dump(exclude={'postgres_url'}))"

# Which GCP service account the key belongs to
uv run python -c "import json, os; from dotenv import load_dotenv; load_dotenv('secrets/.env'); print(json.load(open(os.environ['GOOGLE_APPLICATION_CREDENTIALS']))['client_email'])"

# BigQuery and GCS answer
uv run python -c "from importlib import import_module; c = import_module('src.1_source.config'); s = c.settings(); print(list(c.bq_client(s).query('SELECT 1 AS ok').result())[0].ok, c.gcs_client(s).bucket(s.bucket).exists())"

# Postgres answers (prints 1)
uv run python -c "from importlib import import_module; from sqlalchemy import text; c = import_module('src.1_source.config'); e = c.pg_engine(c.settings()); print(e.connect().execute(text('SELECT 1')).scalar())"
```

## 3. Run code by hand

Normal runs go through Airflow. Use these for one-time loads and debugging.

```bash
uv run python -m src.1_source.load_csv          # one time: course CSVs in data/raw_data -> BigQuery source
uv run python -m src.3_storage.events_bronze    # one time: build events_partitioned (scans about 15 GB); then dbt --select tag:events

# One pipeline step for one data day; steps: ingest bronze silver gold pg_ingest pg_bronze pg_silver pg_gold
uv run python -c "from importlib import import_module; import_module('src.4_transform.run_daily').run_step('2026-10-16', 'pg_ingest', 'manual-debug')"

uv run --extra serving streamlit run src/5_serving/dashboard.py   # dashboard without Docker
uv run python include/scripts/jev_review.py <findings.json>      # Jev scores for a review (needs AI_GATEWAY_API_KEY)
```

## 4. Tests and quality

```bash
uv run pytest                                       # all tests; fails below 100% coverage
uv run pytest tests/test_stages.py -k bronze -q     # a subset
uv run pytest --cov-report=html                     # coverage report in htmlcov/
uv run ruff check . && uv run ruff format --check .
uv run ruff check --fix . && uv run ruff format .   # auto-fix
uvx pre-commit run --all-files                      # same hooks as CI, including gitleaks
```

The DAG test needs Airflow, so it runs in the image, the same way as CI:

```bash
docker compose --env-file secrets/.env --profile airflow build airflow-scheduler
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD/tests:/opt/airflow/tests:ro" --entrypoint bash endtoend-airflow-scheduler -c \
  "pip install --quiet pytest && python -m pytest -q -p no:cacheprovider -o addopts='' /opt/airflow/tests/test_dag_integrity.py"
```

## 5. Logs and debug

| What | Where |
|---|---|
| Script logs | `logs/custom_scripts/unified-data_<env>_<module>_<YYYY-MM-DD>.log` (plain text; console has colors) |
| Log level and env | DEBUG; `STYLEHUB_ENV` (default `prod`) names the file |
| Step history | BigQuery `stylehub_ops.pipeline_runs` |

```bash
tail -50 logs/custom_scripts/unified-data_prod_pipeline_$(date -u +%F).log
grep -h " ERROR " logs/custom_scripts/*.log | tail -20
uv run python -X importtime -c "import pandas" 2>&1 | tail -3   # slow import check
```

Transient GCP, HTTP and Postgres errors retry with backoff (2 s to 60 s, up to 30 minutes) in `src/1_source/retry.py`; a wrong password or missing table fails at once on purpose.
