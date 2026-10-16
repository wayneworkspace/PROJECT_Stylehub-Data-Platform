# dbt project

dbt builds the **Silver** and **Gold** layers and runs their tests.
Bronze is loaded by Python, so dbt only reads it (see `models/staging/stylehub/_stylehub__sources.yaml`).

## Folders (dbt Labs layout)

| Folder | What is inside |
|---|---|
| `models/staging/stylehub/` | `_stylehub__sources.yaml` (the Bronze tables), `_stylehub__models.yaml` (tests) and 5 views `stg_stylehub__orders`, `__order_items`, `__products`, `__users`, `__events`. 1:1 with Bronze: latest row per id, types cast. The only models that call `source()` |
| `models/intermediate/` | 2 views: `int_order_items_joined_to_products` (adds the product cost), `int_orders_joined_to_item_totals` (adds `total_amount`) |
| `models/marts/core/` | 6 tables: `dim_products`, `dim_users`, `fact_orders`, `fact_order_items`, `fact_shipments`, `fact_events` (incremental) |
| `models/marts/reporting/` | 6 Gold tables: `daily_revenue`, `monthly_revenue_by_category`, `return_rate_by_state`, `avg_delivery_days_by_state`, `daily_events_by_type`, `funnel_by_category` |
| `tests/` | Checks written in SQL: item count = num_of_item, no negative prices, Gold total = Silver total, Gold values in range |
| `macros/` | Keeps dataset names as `stylehub_silver` and `stylehub_gold` |

How the dbt Labs names map to ours: staging goes to its own dataset (`stylehub_staging`, it still holds personal data), intermediate and `marts/core` go to the Silver dataset, and all three are built by the `silver` step. `marts/reporting` goes to the Gold dataset and is built by the `gold` step. Tags, materialization and dataset are set per folder in `dbt_project.yml`.

Tests in the `_..._models.yaml` files check the grain (`unique` and `not_null` on the id) and the values (`accepted_values`, `relationships`).

Note: dbt only accepts `.yml` for `dbt_project.yml` and `profiles.yml`. Every other YAML file here uses `.yaml`.

## Run it

PowerShell, from the project folder:

```powershell
uv sync --extra dbt
uv run python -m stylehub.transform.run_dbt silver    # build Silver, then test it
uv run python -m stylehub.transform.run_dbt gold      # build Gold, then test it
```

The command reads `secrets/.env` for you. A failed test stops the step.

Check the project without touching BigQuery:

```powershell
uv run python -m stylehub.transform.run_dbt all --command parse
```

## Good to know

- dbt replaced the old SQL files for Silver, Gold and checks.
- The gold step also runs the test `gold_matches_silver`. That is why the silver step skips tag `gold`.
- Relationship tests only warn. Real data can have orphan ids. Change `severity` to `error` when the data is clean.
- **One Bronze snapshot per run.** The pipeline (`run_dbt.py`) reads the newest Bronze day of each table once and passes it as the variable `bronze_snapshot_dates`. To repeat a run exactly: `dbt build --vars '{bronze_snapshot_dates: {orders: "2026-10-16", order_items: "2026-10-16", products: "2026-10-16", users: "2026-10-16"}}'`. Without the variable, the macro looks up the newest day itself.
- **Contracts.** Five Gold tables (`_reporting__models.yaml`) have `contract: enforced` with a `data_type` for every column. A renamed or re-typed column fails the build before the table is written.
- **Unit tests** (`_reporting__unit_tests.yaml`) check the Gold rules on a few made-up rows: Cancelled orders, Returned orders, a product with no cost, the order of funnel stages, shipped-only return rate. Run only them with `dbt test --select test_type:unit`. They need the Silver tables to exist, because dbt reads the column types from the warehouse. They passed on BigQuery on 2026-10-16. In a unit test, `fact_events.user_session` is a number: a text id becomes NULL and the model returns no rows.
