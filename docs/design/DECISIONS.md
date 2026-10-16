# Design decisions

Record every decision together with real measurements. This is where you answer the interview question "why did you choose this?".

## 1. Partition and cluster for `events` (session 1)

Current setup: `PARTITION BY DATE(event_time) CLUSTER BY event_type, product_id`.

_Not measured yet. Run each query with a dry run and fill in the table. A dry run costs nothing and prints the bytes it would read, for example (PowerShell):_

```powershell
bq query --use_legacy_sql=false --dry_run "SELECT COUNT(*) FROM `PROJECT.stylehub_bronze.events_partitioned` WHERE DATE(event_time) = '2019-11-01'"
```

| Query | Bytes processed | Uses partition/cluster |
|---|---|---|
| Top 10 products purchased in one week | _fill in after measuring_ | partition + cluster |
| Event count per event_type on one day | _fill in_ | partition |
| Full history of one user_id (no date filter) | _fill in_ | no |

If queries by `user_id` are common: add `user_id` to the cluster key, because BigQuery can skip blocks only when the WHERE clause uses a cluster column. Record the measurements before and after the change.

## 2. Watermark for `order_items` (session 2)

Course CSV path (the one `run_daily` uses): the CSV files have no `updated_at` column, so there is no watermark. Every run is a full load, and Silver keeps the latest row of each id (see [ROADMAP.md](ROADMAP.md), session 2).

Short README answering 3 questions: why that column and how many days of lookback; what the Raw Zone contains after a re-run and how duplicates are dropped; whether the pipeline notices when the source deletes a row.

## 3. Sync mode per table (session 4)

_Not started: Airbyte (session 4) is not set up yet. Fill in per table from ARCHITECTURE.md: one sentence of reasoning and the row count compared with the source._

## 4. Star or Snowflake (session 5)

Star by default. Move to Snowflake only when a dimension is very large, has many levels, or its attributes change often.

## 5. Choices made after the code review (please confirm the business ones)

| Topic | Decision | Why / open question |
|---|---|---|
| Course tables path | BigQuery -> pandas -> GCS -> BigQuery stays. | The course dataset is in the US and the bucket is in `asia-southeast1`, so a direct export is not possible. It also matches the course. For big tables, move to a same-region export. |
| Latest snapshot | Silver reads only the newest Bronze snapshot (one partition). A macro finds its date at run time. | Scans one day, not all days. The run fails if Bronze has no partition. |
| Dedupe tie-break | `_ingested_at DESC, _batch_id DESC`. | Two rows with the same id and time now give the same result every run. |
| Returned orders | **Open.** They count as revenue today. | Confirm with the business. Change the status filter in Gold if they should not. |
| Profit | **Open.** It uses the product's current cost, not the cost on the order date. Items with no cost count as 0 cost and are counted in `n_items_without_cost`. | Needs a cost history table to be exact. |
| Marts | `dim_*` and `fact_*` stay in the Silver dataset. | Moving them to Gold breaks the rule "no status filter in Silver". Revisit with a real BI user. |
| PII | `dim_users` keeps `email_hash` (SHA-256) and no lat/long. | This is pseudonymisation, not anonymisation: the same email gives the same hash. |
| `fact_events` | Incremental by `event_date`, newest 3 days. | The events data is static, so no new rows arrive; the incremental logic is not proven by real new data. |
| dbt targets | `dev` is the default and writes to `dbt_<user>_*` datasets. `prod` is used by the pipeline. | A mistake on a laptop cannot overwrite prod tables. |
| Airflow version | Airflow 3.3.2. | See "Airflow 3" in section 8. |

## 6. Choices made after the second review

| Topic | Decision | Why / open question |
|---|---|---|
| Bronze load | Write-Audit-Publish: load into `_stg_<table>`, check the row count against Raw, then copy over the day's partition. | A load that does not match Raw never reaches the partition that Silver reads. After a mismatch the staging table is kept so you can look at it. |
| Freshness check | The older of: the last data date with all 4 steps successful, and the oldest `max(_ingested_at)` of the Bronze tables. | A hand-run `gold` step cannot hide a dead ingest. `sa-monitor` now also needs `bigquery.dataViewer` on the Bronze dataset. |
| One scheduler | Airflow only. `run_on_vm.sh` is for runs by hand. | Cron lines on two VMs hoped that ingest ended before bronze started. |
| Raw retention | Lifecycle rules (`setup_gcp`): live Raw files are deleted after 90 days, old versions after 30 more. | Each day adds a full copy of the source, so Raw only grew. A person's data (the email in the Parquet files) leaves Raw after about 120 days at most. Raw stays append-only, and ingestion still does not clean data. |
| `events` and Raw | `events` still skips the Raw Zone. The three metadata columns are added in `01_events_partitioned.sql`. | 15 GB that never change. Going through Raw needs an export across regions (US to `asia-southeast1`), see section 5. Revisit if events ever get a live source. |
| Pandas path | Not changed. | Same reason as above; an extract job needs the source and the bucket in one region. |
| Revenue rule | One macro, `revenue_order_filter`, reads the dbt variable `revenue_excluded_statuses`. `daily_revenue` now also has `returned_amount` and `net_revenue`. | `revenue` stays gross, so no number changes. Finance picks gross or net. The warn test `item_cancelled_but_order_counted` shows how many Cancelled items sit inside counted orders. |
| Funnel | `funnel_by_category` counts distinct sessions (`n_view_sessions`, ...) and keeps events with an unknown product under `Unknown`. | Counting events let a rate go above 1. The upper bound is the warn test `funnel_rates_at_most_one`. The old columns `n_views`, `n_carts`, `n_purchases` are gone. |
| Silver safety net | The test `bronze_snapshot_not_shrinking` fails if a Bronze snapshot has under 90% of the rows of the one before (`bronze_min_snapshot_ratio`). | Silver is replaced by the newest snapshot, so a cut-off source would shrink Silver and Gold and all other tests would stay green. It reads only Bronze, so `dbt build` runs it before the models. |
| `fact_events` tests | The grain and orphan checks are singular tests on the recent window only. | The generic tests scanned 15 GB every day. Run the full check after a `--full-refresh` (see the test file). |
| dbt login | `method: oauth` (Application Default Credentials) in every target. | One setting works for a key file, a gcloud login, a VM account and Workload Identity in CI. |
| Contracts | Added to five Gold tables, see section 8. | They need the exact BigQuery types, so the first real run may still fail on a wrong type. |

## 7. Choices made after the third review

| Topic | Decision | Why / open question |
|---|---|---|
| Funnel | `funnel_by_category` counts a session at a step only if the step came after the one before (view, then cart, then purchase). The warn on `funnel_rates_at_most_one` is now an error. | Before, a rate could be above 1 and the test only warned. **The funnel numbers change** after this fix. |
| Return rate | `return_rate_by_state` uses only orders that were shipped. | A return needs a shipment. Orders never shipped made the rate too low. |
| Revenue lineage | `daily_revenue` is built from `fact_order_items`, and a new test `silver_matches_bronze` compares counts and money with Bronze. | Gold and Silver could be wrong together. Now Bronze is the second witness. |
| Status test | `fact_orders.status` accepted_values is an error, not a warning. | A new status would silently fall into the revenue rule. |
| PII | dbt staging views go to their own dataset `stylehub_staging` (`BQ_STAGING`). | The views hold raw emails. Give analysts access to Silver and Gold, not to staging. Run `setup_gcp` once, and give `sa-transform` access to the new dataset. |
| Source checks | `extract_full` compares the source columns and row count with what it read, and Raw files keep `source_rows` in their metadata. Bronze compares it with the Parquet footer. | A cut-off read can no longer look like a good day. |
| Cost cap | Default `maximum_bytes_billed` is 50 GB (was lower). | The first `events` build reads about 13 GB. |
| Not done | Silver/Gold are not Write-Audit-Publish; Airflow tasks stay coarse (one task per step); a smaller image per job; pinned base image digests. | Too large for this review, or no way to check them here. Listed in `LIMITATIONS.md`. |

## 8. Choices made after the fourth review

| Topic | Decision | Why / open question |
|---|---|---|
| Bronze history | One full snapshot per day. Silver reads the newest. SCD2 and CDC were not chosen. | The four tables are small, the CSV data has no `updated_at` and there is no change log. Cost: no row history and deleted rows are invisible. Revisit when a live source with `updated_at` or a change log exists. |
| Own run log | `run_step`, `pipeline_runs`, `retry.py` and `load_job_once` are written in this repo. | Every step is a CLI that works with or without Airflow. The run history sits in BigQuery, so the freshness check on GitHub can read it even when Airflow is down. Airflow's own metadata cannot do that. |
| Date label | `--date` names the Raw folder only. The pipeline is full-snapshot. | The source has no `updated_at`, so a back-dated run cannot rebuild the past. The DAG keeps `catchup=False` for this reason. |
| Profit | The Gold column is `profit_at_current_cost`. | It uses the product's cost today. Keeping the cost on the sale day needs a price history that the course data does not have. |
| Contracts and unit tests | Five Gold tables have an enforced contract, and four Gold rules have dbt unit tests. Silver and the incremental `daily_events_by_type` do not. | Gold is what analysts read, so its column names and types are a promise, and the rules (Cancelled, Returned, funnel order, shipped only) are what an interviewer asks about. Written without a BigQuery run: see `LIMITATIONS.md`. |
| Infrastructure as code | Terraform in `infra/terraform/`, approved by the owner on 2026-10-16 (CLAUDE.md changed). | A public portfolio repo should show the cloud setup as code with a plan and least-privilege IAM. Local state, no VMs, `setup_gcp` stays for people who do not use Terraform. Not run yet, see `LIMITATIONS.md`. |
| Data path | Source to pandas to Parquet to GCS to Bronze stays. | Section 6 ("Pandas path"): the source dataset is in the US and the bucket in `asia-southeast1`, so an extract job does not work across them. The four tables are small. |
| Ingestion and transforms | Three small changes happen before Raw: typed empty columns, dropping `user_geom`, and the `absorb` option. | Parquet writes a column of only NULLs with the type `null`, which breaks the BigQuery load of that day. No business rule is applied. |
| Airflow 3 | The DAG and compose file are moved to Airflow 3.3.2. | Airflow 2 is end of life (April 2026). Changes: `airflow.sdk` and `airflow.providers.standard` imports, an API server and a DAG processor instead of the webserver, and `CronDataIntervalTimetable`, because Airflow 3 would otherwise make `ds` the run day and load a day too late. |
