# Getting started

The README has the short version. This page has every step, from the tools you need to the daily run. For one linear walk-through with checks after each step, see [RUN_END_TO_END.md](RUN_END_TO_END.md).

## Prerequisites

| Item | Notes |
|---|---|
| Python 3.11 or newer | Check with `python --version`. |
| [uv](https://docs.astral.sh/uv/) | Installs the packages. |
| Google Cloud project | Turn on the BigQuery and Cloud Storage APIs. |
| GCS bucket | Holds the Raw Zone. |
| Five BigQuery datasets | `stylehub_bronze`, `stylehub_staging`, `stylehub_silver`, `stylehub_gold`, `stylehub_ops`. Use the same location as the bucket. `setup_gcp` creates them. |
| Service account key (JSON) | Save it in `secrets/`. Give the account BigQuery Job User, BigQuery Data Editor and Storage Object Admin. |
| Course CSV files | Five files in `data/raw_data/`. Git ignores them. |
| Docker Desktop (optional) | For the image and Airflow. |

> [!IMPORTANT]
> The StyleHub dataset belongs to the course. This repo holds only code. Do not commit course data or course materials.

## Setup

```powershell
git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform.git
cd PROJECT_Stylehub-Data-Platform
uv sync --extra dev --extra dbt
copy .env.example secrets\.env
uv run pytest
```

Open `secrets\.env` and fill in your values. See [Configuration](CONFIGURATION.md).

## Build the `events` table once

`events` is 108 million rows and never changes, so it is not part of the daily run. Build it one time, after the bucket and datasets exist and the CSV files are loaded:

```powershell
uv run python -m stylehub.bronze.events_bronze
```

It copies `events` into Bronze, builds `events_partitioned`, then deletes the 15 GB copy `events_raw` (add `--keep-raw` to keep it). If you skip this, the bronze step stops and tells you to run this command.

To build the image alone, run `docker build -f deploy/pipeline/Dockerfile -t stylehub-pipeline .`

> [!NOTE]
> The password `stylehub_local` is for this throwaway local database only. The port is open to your own computer and no one else.

## Session 1: set up Google Cloud and load the course CSV files

Put the course CSV files in `data/raw_data/` (Git ignores this folder). Fill in `GCP_PROJECT_ID`, `GCS_BUCKET` and `GCP_LOCATION` in `secrets\.env` first.

```powershell
uv run python -m stylehub.setup.setup_gcp --dry-run   # only print what would be created
uv run python -m stylehub.setup.setup_gcp             # create the bucket and the datasets
uv run python -m stylehub.setup.load_csv --file data/raw_data/orders.csv   # one file first
uv run python -m stylehub.setup.load_csv              # every CSV file in data/raw_data
```

`load_csv` prints the file size and the BigQuery table size, so you can answer the exercise question. `events.csv` is about 16 GB, so uploading it takes a long time.

## First run

After `load_csv` has put the five tables in the `stylehub` dataset, one command runs everything:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "secrets\<your-key>.json"   # only for one-off python -c commands
uv run python -m stylehub.orchestration.run_daily --date 2026-10-01
```

The four steps are:

| Step | What it does |
|---|---|
| `ingest` | Reads `orders`, `order_items`, `products` and `users` from the `stylehub` dataset. Checks the columns. Writes Parquet files to the Raw Zone. |
| `bronze` | Builds the partitioned `events` table if it is missing (copy, then SQL). Loads the latest Raw batch of the day into Bronze. |
| `silver` | Runs the Silver dbt models and their tests. |
| `gold` | Runs the Gold dbt models and their tests. |

The first run is slow because it builds `events` (about 108 million rows). Later runs skip that part, and `fact_events` is incremental: it rebuilds only the newest 3 days. To rebuild all of it, run `dbt build --full-refresh --select fact_events` inside `dbt/`.

To run one step, or to see what the `events` build would scan:

```powershell
uv run python -m stylehub.orchestration.run_daily --date 2026-10-01 --from-step silver --to-step gold
uv run python -m stylehub.bronze.run_sql bronze --dry-run
```

> [!NOTE]
> The `stylehub` dataset may be in a different region (for example US) from Bronze. A BigQuery query cannot read one region and write to another. That is why `events` is copied first.

## Daily run

| Option | How |
|---|---|
| By hand | `uv run python -m stylehub.orchestration.run_daily --date 2026-10-01` |
| Try dbt without touching the real tables | `$env:DBT_DEV_USER = "your-name"` then `uv run python -m stylehub.transform.run_dbt silver --target dev`. dbt writes to `dbt_your-name_stylehub_silver`. |
| Run past dates again | With Airflow: `airflow backfill create --dag-id stylehub_daily --from-date 2026-09-25 --to-date 2026-10-01` (see [deploy/airflow/README.md](../../deploy/airflow/README.md)). Or run `run_daily --date <day>` for each day. |
| Source changed its columns | Ingest stops and names the column. Add `--on-schema-change absorb` to go on anyway (a missing column becomes NULL). |
| Start or stop at a step | Add `--from-step silver` or `--to-step bronze` (steps: ingest, bronze, silver, gold). |
| dbt for Silver and Gold | `uv sync --extra dbt` first. `run_daily` calls dbt in the silver and gold steps, and dbt runs its tests. See [dbt/README.md](../../dbt/README.md). |
| See what ran | Each step is saved in the BigQuery table `stylehub_ops.pipeline_runs`: status, time, rows and error. |
| Get alerts | Set `ALERT_WEBHOOK_URL` to a Discord webhook. A failed step sends one message. |
| On a schedule | Use Airflow (one DAG, `start`, four steps, `end`): [deploy/airflow/README.md](../../deploy/airflow/README.md). You can test the whole DAG for one day with `airflow dags test stylehub_daily 2026-10-15` inside the scheduler container. |

## Checks before you commit

| Check | How | When it runs |
|---|---|---|
| Pre-commit hooks (ruff, gitleaks, file checks) | Run `uvx pre-commit install` once. | On every `git commit` |
| Lint and format | `uv run ruff check .` and `uv run ruff format --check .` | You run them before you push |
| SQL lint | `uv run sqlfluff lint dbt/models dbt/tests` | You run it before you push |
| Type check | `uv run mypy` | You run it before you push. Needs `uv sync --extra dev` |
| Unit tests | `uv run pytest --cov` (fails below the coverage limit) | You run them before you push |
| CI on GitHub | Same checks, plus `dbt parse`, a package scan, a Docker build and an image scan | On every push to `main` and every pull request |

See [docs/ops/DEVOPS.md](DEVOPS.md) for what each CI job does.
