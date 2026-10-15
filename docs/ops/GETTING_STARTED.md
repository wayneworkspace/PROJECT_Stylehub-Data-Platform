# Getting started

The README has the short version. This page has every step, from the tools you need to the daily run. For one linear walk-through with checks after each step, see [RUN_END_TO_END.md](RUN_END_TO_END.md).

## Prerequisites

| Item | Notes |
|---|---|
| Python 3.11 or newer | Check with `python --version`. |
| [uv](https://docs.astral.sh/uv/) | Installs the packages. |
| Google Cloud project | Turn on the BigQuery and Cloud Storage APIs. |
| GCS bucket | Holds the Raw Zone. |
| Four BigQuery datasets | `stylehub_bronze`, `stylehub_silver`, `stylehub_gold`, `stylehub_ops`. Use the same location as the bucket. `setup_gcp` creates them. |
| Service account key (JSON) | Save it in `secrets/`. Give the account BigQuery Job User, BigQuery Data Editor and Storage Object Admin. |
| Course CSV files | Five files in `data/raw_data/`. Git ignores them. Postgres access is only needed for the optional Postgres path. |
| Docker Desktop (optional) | For the local Postgres and the image. You can try ingestion without any cloud account. |

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

## Try it with Docker (no cloud needed)

The local Postgres holds a small set of sample orders. You can test the extraction step with it. Nothing is written to GCS.

```powershell
docker compose up -d --wait postgres
docker compose run --rm pipeline python -m ingestion.optional.database --table orders --date 2026-10-01 --dry-run
```

`--wait` makes the first command wait until Postgres is ready. The second command should print a line like `orders 2026-10-01: 24 rows (incremental, 0.1s, dry run, nothing written)`. To run the integration tests against the same database:

```powershell
$env:PG_HOST = "localhost"; $env:PG_PORT = "5432"; $env:PG_DATABASE = "stylehub"
$env:PG_USER = "stylehub"; $env:PG_PASSWORD = "stylehub_local"
uv run pytest -m integration
docker compose --profile dev --profile pipeline down -v
```

To build the image alone, run `docker build -f deploy/pipeline/Dockerfile -t stylehub-pipeline .`

> [!NOTE]
> The password `stylehub_local` is for this throwaway local database only. The port is open to your own computer and no one else.

## Session 1: set up Google Cloud and load the course CSV files

Put the course CSV files in `data/raw_data/` (Git ignores this folder). Fill in `GCP_PROJECT_ID`, `GCS_BUCKET` and `GCP_LOCATION` in `secrets\.env` first.

```powershell
uv run python -m storage.setup.setup_gcp --dry-run   # only print what would be created
uv run python -m storage.setup.setup_gcp             # create the bucket and the datasets
uv run python -m storage.setup.load_csv --file data/raw_data/orders.csv   # one file first
uv run python -m storage.setup.load_csv              # every CSV file in data/raw_data
```

`load_csv` prints the file size and the BigQuery table size, so you can answer the exercise question. `events.csv` is about 16 GB, so uploading it takes a long time.

## First run

After `load_csv` has put the five tables in the `stylehub` dataset, one command runs everything:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "secrets\<your-key>.json"   # only for one-off python -c commands
uv run python -m orchestration.run_daily --date 2026-10-01
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
uv run python -m orchestration.run_daily --date 2026-10-01 --from-step silver --to-step gold
uv run python -m transform.run_sql bronze --dry-run
```

> [!NOTE]
> The `stylehub` dataset may be in a different region (for example US) from Bronze. A BigQuery query cannot read one region and write to another. That is why `events` is copied first.

## Daily run

| Option | How |
|---|---|
| By hand | `uv run python -m orchestration.run_daily --date 2026-10-01` |
| Postgres or API source (not in `run_daily`) | `uv run python -m ingestion.optional.api --table users --date 2026-10-01 --dry-run`. Needs `API_KEY` in `secrets/.env`. Remove `--dry-run` to write to the Raw Zone. |
| Load a whole table | Add `--full-load`: `uv run python -m ingestion.optional.database --table orders --date 2026-10-01 --full-load`. Add `--dry-run` to only count. |
| Run past dates again | With Airflow: `airflow dags backfill stylehub_daily -s 2026-09-25 -e 2026-10-01` (see [deploy/airflow/README.md](../../deploy/airflow/README.md)). Or run `run_daily --date <day>` for each day. |
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
| Lint | `uv run ruff check .` | You run it before you push |
| Unit tests | `uv run pytest` | You run them before you push |
| Integration tests | `uv run pytest -m integration` (needs the Docker Postgres) | You run them before you push |
| CI on GitHub | Same checks, plus `dbt parse` and a Docker build | On every push to `main` and every pull request |

See [docs/ops/DEVOPS.md](DEVOPS.md) for what each CI job does.
