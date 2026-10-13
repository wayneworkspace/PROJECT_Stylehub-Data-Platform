# StyleHub Data Platform

A data platform on GCP for the StyleHub dataset (users, products, orders, order_items, shipments, and events with ~108 million rows), built to follow a 5-session curriculum. The structure is designed so that dbt, Airflow and Spark can be added later without rewriting anything.

```
Postgres + API ─► Raw Zone (GCS) ─► Bronze ─► Silver (fact/dim) ─► Gold
   (Python / Airbyte)            (BigQuery, 3 datasets)
```

## Repo layout by session

| Session | Topic | Where |
|---|---|---|
| 1 | GCS + BigQuery, partition/cluster, measuring bytes processed | `sql/bronze/01_events_partitioned.sql`, `docs/DECISIONS.md` |
| 2 | Ingestion, watermark, incremental load, Raw Zone | `ingestion/` |
| 3 | Transform, Medallion Bronze/Silver/Gold | `pipeline/load_bronze.py`, `sql/silver/`, `sql/gold/` |
| 4 | Ingestion tool (Airbyte), sync modes | `docs/ARCHITECTURE.md` (Airbyte runs on a VM, configured in its UI) |
| 5 | Data modeling: grain, fact, dimension, star | `sql/silver/` (5 tables), `sql/gold/` (4 tables) |

`pipeline/` ties the steps together. `sql/checks/` holds the data quality checks.

## Run

```bash
cp .env.example .env        # fill in values, never commit
make setup
make test

make ingest DATE=2026-10-01   # Postgres -> Raw Zone
make bronze DATE=2026-10-01   # Raw Zone -> Bronze (append)
make silver                   # Bronze -> Silver
make gold                     # Silver -> Gold
make check                    # grain, amount, Gold-vs-Silver reconciliation
make daily DATE=2026-10-01    # run the whole chain above

uv run python -m pipeline.run_sql gold --dry-run   # only print bytes processed
```

Prerequisites: a GCP project, a GCS bucket, three datasets (`stylehub_bronze`, `stylehub_silver`, `stylehub_gold`) and a service account with GCS + BigQuery access.

## Notes

- Column names in `sql/silver/` were inferred from the homework assignments and slides. Check them against the real schema in BigQuery (especially `users` and `shipments`) before running.
- If Bronze is loaded by Airbyte, the metadata column is `_airbyte_extracted_at`, not `_ingested_at`. Change it in the `sql/silver/` files.
- To extend with dbt, Airflow or Spark, see [docs/EXTENDING.md](docs/EXTENDING.md).
- The StyleHub dataset belongs to the course. This repo contains only self-built code. Never commit `secrets/`, `.env`, GCP keys or CSV data.
