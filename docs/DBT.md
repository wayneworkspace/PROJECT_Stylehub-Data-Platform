# dbt Commands

Build, test, inspect and debug the models in `dbt_project/`. Commands are `bash` (Git Bash) from the project folder.

dbt reads its settings from environment variables, so load `secrets/.env` first. `dotenv run` handles the comments in that file; `uv run --env-file` does not.

```bash
DBT="uv run dotenv -f secrets/.env run -- dbt"
P="--project-dir dbt_project --profiles-dir dbt_project"
```

## 1. Connection and paths

| Item | Value | Where |
|---|---|---|
| Version | dbt-core with dbt-bigquery 1.12 | `pyproject.toml` extra `dbt` |
| Profile | `stylehub`, target `prod`, `method: oauth` (key file, gcloud login or VM account) | `dbt_project/profiles.yml` |
| Project and location | `GCP_PROJECT_ID`, `GCP_LOCATION` (`asia-southeast1`) | `secrets/.env` |
| Account | The key in `GOOGLE_APPLICATION_CREDENTIALS`; in CD, `sa-pipeline` through Workload Identity | `secrets/.env`, `cd_deploy.yml` |
| Cost cap | `BQ_MAX_BYTES_BILLED` (50 GB per query) | `secrets/.env` |
| Compiled SQL | `dbt_project/target/<layer>/compiled/...` and `.../run/...` | `--target-path` |
| Logs | `logs/dbt/<layer>/dbt.log` (JSON lines) | `--log-path` |

## 2. Layers, tags and datasets

| Tag (DAG step) | Folders | Dataset | Materialized |
|---|---|---|---|
| `silver` | `staging/stylehub` | `stylehub_staging` | view |
| `silver` | `intermediate`, `marts/core`, snapshot `products_history` | `stylehub_silver` | view / table / snapshot |
| `gold` | `marts/reporting` | `stylehub_gold` | table |
| `pg_silver` | `staging/stylehub_pg` | `stylehub_staging` | view |
| `pg_silver` | `marts/pg_core` | `stylehub_silver` | table |
| `pg_gold` | `marts/pg_reporting`, test `pg_gold_matches_silver` | `stylehub_gold` | table |

Staging views still hold email and location: keep analysts on Silver and Gold.

## 3. Operate

```bash
# The same command the pipeline runs for one layer (src/4_transform/run_dbt.py)
$DBT build $P --target-path target/pg_gold --log-path logs/dbt/pg_gold --fail-fast --indirect-selection cautious --select tag:pg_gold

$DBT build $P --log-path logs/dbt --select pg_daily_revenue            # one model and its tests
$DBT build $P --log-path logs/dbt --select pg_fact_orders+             # a model and everything after it
$DBT run   $P --log-path logs/dbt --select tag:pg_silver               # models only, no tests
$DBT test  $P --log-path logs/dbt --select tag:pg_gold                 # tests only
$DBT snapshot $P --log-path logs/dbt                                   # SCD2 products_history
$DBT build $P --log-path logs/dbt --fail-fast --indirect-selection cautious   # everything, like CD
```

Keep `--indirect-selection cautious`: without it, a Silver build also runs Gold tests whose tables do not exist yet.

## 4. Check

| Check | Command | Healthy result |
|---|---|---|
| Connection | `$DBT debug $P --log-path logs/dbt` | `All checks passed!` |
| Project parses | `GCP_PROJECT_ID=ci GCS_BUCKET=ci uv run dbt parse $P --log-path logs/dbt` | No error (same as CI) |
| What a tag selects | `$DBT ls $P --log-path logs/dbt --select tag:pg_gold --resource-type model` | The model list |
| SQL style | `uv run sqlfluff lint dbt_project/models dbt_project/macros dbt_project/tests include/sql` | `All Finished!` |
| Source freshness | `$DBT source freshness $P --log-path logs/dbt` | `PASS` or `WARN` |
| Last result | `grep -h '"Done. PASS' logs/dbt/*/dbt.log \| tail -3` | `ERROR=0` |

## 5. Debug

```bash
# First real error of the last pg_gold build (later "Not found: Job" lines are fail-fast cancels)
grep '"level": "error"' logs/dbt/pg_gold/dbt.log | uv run python -c "
import sys, json
for line in sys.stdin: print(json.loads(line)['info']['msg'][:300])" | head -5

$DBT compile $P --log-path logs/dbt --select pg_monthly_top_customers   # see the final SQL
cat dbt_project/target/pg_gold/compiled/stylehub/models/marts/pg_reporting/pg_monthly_top_customers.sql

$DBT show $P --log-path logs/dbt --select pg_daily_revenue --limit 5     # preview rows
$DBT docs generate $P --log-path logs/dbt && $DBT docs serve $P --port 8090   # lineage in a browser
```

| Warning or error | Meaning |
|---|---|
| `relationships_pg_fact_order_items_order_id ...` WARN | Items whose order is missing (first full load); known, does not fail the run |
| `Ordering by expressions of type STRUCT` | A CTE has the same name as a column |
| `Not found: Job ...` on many models | Fail-fast cancelled the others; look for the first `ERROR in model` |
