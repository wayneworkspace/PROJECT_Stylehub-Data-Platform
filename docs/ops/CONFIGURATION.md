# Configuration

Settings come from `secrets/.env` (copy `.env.example` first). Python reads them in `src/stylehub/common/config.py`.

| Item | Where | Notes |
|---|---|---|
| `GCP_PROJECT_ID` | `secrets/.env` | Required. |
| `GCP_LOCATION` | `secrets/.env` | Where `setup_gcp` creates the bucket and datasets. Default `asia-southeast1`. Use one location for all of them. The `stylehub` course dataset may be elsewhere. |
| `GCS_BUCKET` | `secrets/.env` | Required. Bucket name only, with no `gs://`. |
| `GOOGLE_APPLICATION_CREDENTIALS` | `secrets/.env` (optional) | Path to a service account JSON, for example `secrets/gcp-sa.json`. Prefer `gcloud auth application-default login` on a laptop and nothing here: a key file is a long-lived password. A relative path is counted from the project folder. Never commit it. |
| `RAW_PREFIX` | `secrets/.env` | Folder for Raw files. Default `raw/stylehub`. |
| `BQ_SOURCE` | `secrets/.env` | Dataset with the course's original tables, such as `events`. Default `stylehub`. |
| `BQ_BRONZE`, `BQ_STAGING`, `BQ_SILVER`, `BQ_GOLD` | `secrets/.env` | Dataset names. Defaults `stylehub_bronze`, `stylehub_staging`, `stylehub_silver`, `stylehub_gold`. `stylehub_staging` holds the staging views, which still contain email and exact location: do not give analysts access to it. |
| `BQ_MAX_BYTES_BILLED` | `secrets/.env` (optional) | BigQuery refuses any query that would bill more bytes than this, in Python and in dbt. Default 50 GB (about 0.31 USD), about three times the biggest query (building `events`, about 15 GB), so a wrong query is stopped. Raise it on purpose for a bigger one. |
| `DBT_DEV_USER` | Your shell (optional) | Your name for a dbt run by hand. dbt then writes to `dbt_<name>_stylehub_silver` and `..._gold`. The pipeline always uses the real datasets (dbt target `prod`). |
| `BQ_OPS` | `secrets/.env` | Dataset for `pipeline_runs`. Default `stylehub_ops`. Create it before the first run. |
| `DBT_TIMEOUT_SECONDS` | `secrets/.env` (optional) | Stops one dbt command that runs longer than this many seconds. Default 3600. A stopped command is a failed step. |
| `ALERT_WEBHOOK_URL` | `secrets/.env` (optional) | Discord webhook for failure alerts. It is a secret. Leave it empty to turn alerts off. |
| Bronze snapshot retention | `SNAPSHOT_RETENTION_DAYS` in `src/stylehub/bronze/load_bronze.py` | Default 30. BigQuery deletes older day-partitions by itself. Silver reads only the newest one. |

> [!WARNING]
> Never commit `secrets/` (it holds `.env` and the key file), GCP keys or passwords. `.gitignore` blocks them, but check `git status` before each commit.
