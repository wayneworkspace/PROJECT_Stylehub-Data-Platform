# Roadmap by session

## Session 1: Data Platform
- [ ] GCP project, GCS bucket, three BigQuery datasets, service account
- [ ] Upload CSVs to GCS, load the 5 tables into BigQuery, compare bytes processed with the original file size
- [ ] `events_partitioned` (`sql/bronze/01_events_partitioned.sql`)
- [ ] Measure 3 queries and record them in `docs/DECISIONS.md`, section 1

## Session 2: Data Ingestion
- [ ] Check `updated_at` of order_items, then choose the watermark (`docs/DECISIONS.md`, section 2)
- [ ] `make ingest` for orders and order_items; backfill 7 days; re-running does not change the distinct id count
- [ ] Ingest `products` from the API into `raw/stylehub/products_api/` (overwrite per day)

## Session 3: Transform and layering
- [ ] `make bronze` loads orders, order_items, products
- [ ] Silver `fact_orders`, `fact_order_items`, `dim_products`
- [ ] Gold `daily_revenue`, `make check` passes

## Session 4: Ingestion tool
- [ ] Airbyte VM on GCP, firewall restricted to your own IP
- [ ] Postgres → BigQuery connections for orders, order_items, products, shipments
- [ ] Connector Builder for the StyleHub API
- [ ] Record the sync mode of each table in `docs/DECISIONS.md`, section 3

## Session 5: Data modeling
- [ ] Fill in the design table (question, event, grain, measure, dimensions) for the 5 questions
- [ ] All 5 Silver tables built, `make check` passes the grain check
- [ ] Gold: revenue by category, return rate, delivery time

## After the curriculum
See [EXTENDING.md](EXTENDING.md): dbt, Airflow, Spark. Also add daily incremental data (1,000 to 4,000 rows) so the pipeline runs for real.
