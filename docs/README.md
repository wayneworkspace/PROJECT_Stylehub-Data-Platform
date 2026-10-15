# Docs: where to start

Not sure which page to open? Find your goal in the first table.

## Pick by goal

| I want to... | Open |
|---|---|
| Set up the tools and run the pipeline | [GETTING_STARTED.md](ops/GETTING_STARTED.md) |
| Run the whole pipeline for the first time | [RUN_END_TO_END.md](ops/RUN_END_TO_END.md) |
| Look up a setting in `secrets/.env` | [CONFIGURATION.md](ops/CONFIGURATION.md) |
| Fix an error | [TROUBLESHOOTING.md](ops/TROUBLESHOOTING.md) |
| Understand how the layers fit together | [ARCHITECTURE.md](design/ARCHITECTURE.md) |
| See the data flow as a picture | [html/architecture.html](html/architecture.html) (open in a browser) |
| Read the main code line by line | [html/code-walkthrough.html](html/code-walkthrough.html) (open in a browser) |
| Know why we choose ELT and where rules live | [ETL_VS_ELT.md](design/ETL_VS_ELT.md) |
| Know why a design choice was made | [DECISIONS.md](design/DECISIONS.md) |
| Change a business rule or add a table | [EXTENDING.md](design/EXTENDING.md) |
| Understand CI, Docker and pre-commit | [DEVOPS.md](ops/DEVOPS.md) |
| Publish the Docker image | [CD.md](ops/CD.md) |
| Run the pipeline on a GCP VM | [DEPLOY_VM.md](ops/DEPLOY_VM.md) |
| See what is done and what comes next | [ROADMAP.md](design/ROADMAP.md) |
| See what the project cannot do yet | [LIMITATIONS.md](design/LIMITATIONS.md) |

## Folders

| Folder | What is inside |
|---|---|
| `design/` | Why the pipeline looks this way: architecture, decisions, ELT, extending, limitations, roadmap |
| `ops/` | How to run and ship it: getting started, configuration, troubleshooting, end-to-end run, DevOps, CD, GCP VM |
| `html/` | Pages to open in a browser |
| `assets/` | Images for the docs |

## Suggested reading order

| Step | Page | Why |
|---|---|---|
| 1 | [../README.md](../README.md) | What the project does and how to start |
| 2 | [ARCHITECTURE.md](design/ARCHITECTURE.md) | The layers: Raw, Bronze, Silver, Gold |
| 3 | [RUN_END_TO_END.md](ops/RUN_END_TO_END.md) | Run it yourself and check each step |
| 4 | [DECISIONS.md](design/DECISIONS.md) | The reasons behind the design |
| 5 | The rest | Open them when you need them |

## Other READMEs in the repo

| Folder | What it explains |
|---|---|
| [../dbt/README.md](../dbt/README.md) | The dbt models, folders and tests |
| [../deploy/airflow/README.md](../deploy/airflow/README.md) | How to run Airflow and the daily DAG |
| [../CLAUDE.md](../CLAUDE.md) | Rules for anyone who changes the code |

## Project structure

```
.
├── .github/
│   └── workflows/
│       ├── ci.yaml          # Checks that run on every push to main
│       ├── cd.yaml          # Pushes the image to Artifact Registry after CI
│       └── freshness.yaml   # Daily "did the pipeline run?" check (alert from outside Airflow)
├── data/                    # Your local course CSV files. Git ignores this folder.
├── deploy/                  # Everything that runs: one folder per part (compose file is in the root)
│   ├── pipeline/
│   │   ├── Dockerfile       # Image for the pipeline (CD publishes it)
│   │   └── run_on_vm.sh     # Run one pipeline step inside Docker on a VM
│   └── airflow/
│       ├── dags/stylehub_daily.py  # Daily DAG: start -> ingest -> bronze -> silver -> gold -> end
│       ├── Dockerfile       # Image for Airflow, with the pipeline packages inside
│       └── README.md        # How to run Airflow
├── dev/                     # Sample data for local tests (never deployed)
│   └── postgres/init/       # Seed SQL for the local Postgres
├── dbt/                     # Silver and Gold as dbt models, with tests
│   ├── models/              # dbt Labs layout, see the table below
│   │   ├── staging/stylehub/       # stg_stylehub__*: 1:1 with Bronze, latest row, cast types
│   │   ├── intermediate/           # int_*: joins and totals
│   │   └── marts/                  # core/ (dim_, fact_) and reporting/ (Gold business tables)
│   ├── tests/               # Checks that compare layers and test values
│   └── README.md            # How to run dbt
├── docs/
│   ├── README.md            # Start here: which page to read for which goal
│   ├── assets/              # Icons used in the README
│   ├── html/                # Pages to open in a browser
│   │   ├── architecture.html       # Data flow diagram
│   │   └── code-walkthrough.html   # Line-by-line guide to the main code
│   ├── design/              # Why the pipeline is built this way
│   │   ├── ARCHITECTURE.md  # Layers, star schema, Airbyte sync modes
│   │   ├── DECISIONS.md     # Design choices and measurements
│   │   ├── ETL_VS_ELT.md    # Why ELT, and what to change when a business rule changes
│   │   ├── EXTENDING.md     # How to add dbt, Airflow and Spark later
│   │   └── ROADMAP.md       # Plan by course session
│   └── ops/                 # How to run and ship it
│       ├── RUN_END_TO_END.md  # Step-by-step: run the whole pipeline
│       ├── CD.md              # Publish the image and let the VM pull it
│       ├── DEPLOY_VM.md       # Run the pipeline on a GCP VM
│       └── DEVOPS.md          # CI, Docker, pre-commit and what comes next
├── src/
│   ├── python/
│   │   ├── common/
│   │   │   ├── config.py            # Settings and SQL placeholders
│   │   │   └── retry.py             # Try again, with growing waits, after a short BigQuery or GCS error
│   │   ├── ingestion/               # 1. Ingestion: source -> Raw Zone, unchanged
│   │   │   ├── csv_tables.py        # Course tables -> Raw Zone: full load (used by the pipeline)
│   │   │   ├── schema_check.py      # Stop when the source changes its columns
│   │   │   ├── raw_writer.py        # Write Parquet and metadata columns to GCS
│   │   │   └── optional/            # NOT used by run_daily. Kept for a live Postgres or API source
│   │   │       ├── database.py      # Postgres -> Raw Zone: incremental or full load
│   │   │       ├── api.py           # StyleHub API -> Raw Zone
│   │   │       └── sources/         # The clients: postgres.py and stylehub_api.py
│   │   ├── storage/                 # 2. Storage: the daily Bronze steps
│   │   │   ├── load_bronze.py       # Raw Zone -> Bronze (latest batch of the day)
│   │   │   ├── copy_events.py       # Copy events from the US dataset to Bronze (one time)
│   │   │   ├── events_bronze.py     # Build events_partitioned if it is missing
│   │   │   └── setup/               # Run once by hand, not by run_daily (session 1)
│   │   │       ├── setup_gcp.py     # Create the bucket and the datasets
│   │   │       └── load_csv.py      # Local CSV -> bucket -> BigQuery
│   │   ├── transform/               # 3. Transform: dbt for Silver and Gold
│   │   │   ├── run_sql.py           # Run the SQL files of the Bronze layer
│   │   │   └── run_dbt.py           # Run dbt for Silver or Gold (models + tests)
│   │   └── orchestration/           # Runs the stages in order
│   │       ├── run_daily.py         # Run all steps for one date, with logs and alerts
│   │       ├── runs.py              # Save one row per step in BigQuery (keeps a file copy if that fails)
│   │       ├── alerts.py            # Send a message when a step fails
│   │       └── check_freshness.py   # Alert when no good run happened lately
│   ├── sql/
│   │   ├── bronze/                  # Table setup (partitioned events)
│   │   └── ops/                     # The pipeline_runs table
│   └── tests/                       # Same stages as src/python
│       ├── ingestion/               # Raw Zone writer, schema check, full load
│       │   └── optional/            # Postgres and API code: clients, window, integration tests
│       ├── storage/                 # Bronze load, events copy
│       │   └── setup/               # Bucket, datasets, CSV load
│       ├── transform/               # SQL files, dbt project, business rules
│       ├── orchestration/           # Run history, alerts, Airflow DAG
│       └── common/                  # Config
├── .dockerignore
├── .env.example             # Names of ALL settings (pipeline and Airflow). Copy to secrets/.env.
├── .gitignore
├── .pre-commit-config.yaml  # Checks that run before each commit
├── Makefile                 # `make clean` removes caches and dbt build output
├── CLAUDE.md                # Rules for AI assistants and contributors
├── docker-compose.yaml      # ONE compose file. Profiles: dev (sample Postgres), pipeline, airflow
├── pyproject.toml           # Dependencies and tool settings
├── README.md
└── uv.lock                  # Exact package versions
```

> [!TIP]
> Read `CLAUDE.md` before you change code. It lists the rules for SQL, ingestion and secrets.

> [!NOTE]
> Some pages describe the VM path (`ops/DEPLOY_VM.md`, `ops/CD.md`). They are a starting point only. Airflow schedules the pipeline.
