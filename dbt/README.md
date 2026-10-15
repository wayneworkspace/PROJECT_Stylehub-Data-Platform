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

How the dbt Labs names map to ours: staging, intermediate and `marts/core` go to the Silver dataset and are built by the `silver` step. `marts/reporting` goes to the Gold dataset and is built by the `gold` step. Tags, materialization and dataset are set per folder in `dbt_project.yml`.

Tests in the `_..._models.yaml` files check the grain (`unique` and `not_null` on the id) and the values (`accepted_values`, `relationships`).

Note: dbt only accepts `.yml` for `dbt_project.yml` and `profiles.yml`. Every other YAML file here uses `.yaml`.

## Run it

PowerShell, from the project folder:

```powershell
uv sync --extra dbt
uv run python -m transform.run_dbt silver    # build Silver, then test it
uv run python -m transform.run_dbt gold      # build Gold, then test it
```

The command reads `secrets/.env` for you. A failed test stops the step.

Check the project without touching BigQuery:

```powershell
uv run python -m transform.run_dbt all --command parse
```

## Good to know

- dbt replaced the old SQL files for Silver, Gold and checks.
- The gold step also runs the test `gold_matches_silver`. That is why the silver step skips tag `gold`.
- Relationship tests only warn. Real data can have orphan ids. Change `severity` to `error` when the data is clean.
