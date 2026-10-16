# StyleHub Data Pipeline

[![CI](https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform/actions/workflows/ci.yaml/badge.svg)](https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform/actions/workflows/ci.yaml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![GCP](https://img.shields.io/badge/cloud-GCP-4285F4)

An ELT data pipeline on Google Cloud for an online-shop dataset. Built with Python and SQL for loading, dbt on BigQuery for transforms, and Airflow for the daily schedule.

## Overview

The StyleHub Data Pipeline moves raw shop data to business-ready tables in one flow:

- **Ingestion**: Read the course tables and write Parquet files to a Raw Zone on Google Cloud Storage (append-only, with metadata columns)
- **Bronze loading**: Load the latest batch of each day into BigQuery. Running a day twice does not double the rows
- **Transforms**: dbt builds Silver (facts and dimensions) and Gold (business tables) and runs its tests
- **Large table handling**: The `events` table (about 108 million rows) is partitioned, clustered and loaded incrementally
- **Operations**: Run history in BigQuery, Discord alerts on failure, and a daily "did it run?" check
- **Scheduling**: One Airflow DAG runs the four steps every day

> Built while following a 5-session data engineering course. The pipeline has run end to end on a real BigQuery project. See [Limitations](#limitations) for what has not been tested yet.

<p align="center"><img src="docs/assets/StyleHub%20Data%20Pipeline%20Architecture.png" alt="StyleHub data pipeline architecture on Google Cloud: sources, Airflow, Raw Zone, Bronze, Silver, Gold, monitoring and CI/CD" width="900" /></p>

## Results

| What | Result |
|---|---|
| Data size | 5 tables, about 108 million event rows (a 16 GB CSV) |
| Data quality checks | Silver: 50 dbt nodes (13 models, 37 tests). Gold: 38 nodes (6 models, 28 tests, 4 unit tests, 5 enforced contracts). All passed on a real BigQuery run on 2026-10-16 |
| Cost control | `fact_events` is incremental: a daily run rebuilds the newest 3 days (about 2.7 GiB scanned on 2026-10-16), not the whole 15 GB table |
| Safe re-runs | Running the same day twice does not add rows (one batch per day in Bronze) |
| Tests | Unit tests, ruff, pre-commit (including gitleaks) and a Docker build run in CI |
| Run history | Every step is saved in `stylehub_ops.pipeline_runs`, with a Discord alert on failure |

## Tech Stack

### Cloud and storage

| Technology | Role |
|---|---|
| Google Cloud Storage | Raw Zone, Parquet files |
| BigQuery | Bronze, Silver, Gold and run history |
| google-cloud-bigquery 3.46.1, google-cloud-storage 3.1.1 | Python clients |

### Processing and transforms

| Technology | Role |
|---|---|
| Python 3.12 (the same in CI, Docker and Airflow) | Ingestion, loading and orchestration code |
| pandas 3.0.6, PyArrow 26.0.0 | Read tables and write Parquet |
| dbt-core 1.12.5, dbt-bigquery 1.12.1 | Silver and Gold models, with data tests |
| requests 2.34.2 | Failure alerts (Discord webhook) |

### Orchestration

| Technology | Role |
|---|---|
| Apache Airflow 3.3.2 | Daily DAG (ingest, bronze, silver, gold). The Docker image builds and a test run of all tasks passed on real GCS and BigQuery; a run started by the scheduler has not happened yet, see [LIMITATIONS.md](docs/design/LIMITATIONS.md) |

### DevOps and tooling

| Technology | Role |
|---|---|
| Docker, Docker Compose | Pipeline image and Airflow |
| Terraform | Bucket, datasets, service accounts, image repository and the GitHub login as code (`infra/terraform/`). Applied to the real project on 2026-10-16; the next `plan` says no changes |
| GitHub Actions | CI (lint, tests, dbt parse, SQL lint, package and image scan, SBOM), CD (pushes the image CI tested), daily freshness check |
| uv | Package manager with a lock file |
| pytest 9.1.1, ruff 0.17.0, sqlfluff | Tests, Python lint and format, SQL lint |
| pre-commit, gitleaks 8.30.1 | Checks before each commit, including a secrets scan |

## Key design decisions

| Decision | Why |
|---|---|
| ELT, not ETL | Raw data is kept, so a business rule change means re-running SQL, not re-reading the source. See [ETL_VS_ELT.md](docs/design/ETL_VS_ELT.md). |
| Business rules live in Gold | Silver says what the data is. Gold says what a number means. Changing "revenue" rebuilds Gold only. |
| Raw Zone is append-only | Every run writes a new `batch_id`. Nothing is overwritten, so any layer can be rebuilt. |
| `events` is partitioned and clustered | Partition by day, cluster by `event_type` and `product_id`, so queries scan only what they need. |
| Every step is a CLI with `--date` | Each step runs alone and is safe to run again. Airflow and `run_daily` call the same code. |
| Python for ingestion, dbt for transforms | Airflow's package versions clash with the pipeline's, so Python steps run in a separate environment. |

More reasons and measurements: [docs/design/DECISIONS.md](docs/design/DECISIONS.md).

## Quick start

You need [uv](https://docs.astral.sh/uv/), a Google Cloud project and a service account key.

```powershell
git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform.git
cd PROJECT_Stylehub-Data-Platform
uv sync --extra dev --extra dbt
copy .env.example secrets\.env      # then fill in your values
uv run pytest
uv run python -m stylehub.orchestration.run_daily --date 2026-10-01
```

Build the big `events` table once before the first daily run: `uv run python -m stylehub.bronze.events_bronze`. Every setting is explained in [docs/ops/CONFIGURATION.md](docs/ops/CONFIGURATION.md). Full steps (create the bucket, load the CSV files, schedule with Airflow): [docs/ops/GETTING_STARTED.md](docs/ops/GETTING_STARTED.md) and [docs/ops/RUN_END_TO_END.md](docs/ops/RUN_END_TO_END.md).

## Project layout

```
src/stylehub/   ingestion/  bronze/  setup/  transform/  orchestration/  common/
src/stylehub/sql/   Bronze and ops tables (inside the package)
dbt/          Silver and Gold models and tests
deploy/       Dockerfiles and the Airflow DAG
infra/        Terraform for the Google Cloud setup
docs/         design/ (why) and ops/ (how to run)
```

The full tree with a note for every file: [docs/README.md](docs/README.md#project-structure).

## Limitations

- This is a full-snapshot pipeline, not an incremental one. The source has no `updated_at`, so every run reads whole tables, and `--date` is only the label of the Raw folder: a back-dated run does not rebuild the past.
- Bronze keeps one full copy per day and Silver reads the newest. There is no row history and no way to see deleted rows (see DECISIONS.md, section 8).
- The pipeline reads the course tables in BigQuery. There is no live source yet (Airbyte is not set up).
- Airflow 3 runs in Docker on a laptop (a test run of all tasks passed on real GCS and BigQuery). A run started by the scheduler has not happened yet, and nothing has run on a GCP VM.
- One service account does everything on a laptop. One VM per job, each with its own service account and no key file, is designed in `DEPLOY_VM.md` but not created.
- Backups are only the Raw Zone (GCS versioning) and BigQuery time travel.
- The BigQuery, dbt macro and workflow changes in `docs/design/LIMITATIONS.md` have been tested with fakes and `dbt parse` only, not on real BigQuery or GitHub.

The complete list: [docs/design/LIMITATIONS.md](docs/design/LIMITATIONS.md)

## Learn more

| I want to... | Open |
|---|---|
| Set up and run the pipeline | [GETTING_STARTED.md](docs/ops/GETTING_STARTED.md) |
| Look up a setting | [CONFIGURATION.md](docs/ops/CONFIGURATION.md) |
| Understand the layers | [ARCHITECTURE.md](docs/design/ARCHITECTURE.md) |
| See the data flow as a picture | [architecture.html](docs/html/architecture.html) |
| Read the main code line by line | [code-walkthrough.html](docs/html/code-walkthrough.html) |
| Fix an error | [Troubleshooting](docs/ops/TROUBLESHOOTING.md) |
| See the plan | [ROADMAP.md](docs/design/ROADMAP.md) |

> The StyleHub dataset belongs to the course. This repo holds only code. Never commit `secrets/`, keys or the raw CSV files.
