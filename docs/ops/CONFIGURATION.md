# Configuration

Settings come from `secrets/.env` (copy `.env.example` first). Python reads them in `src/python/common/config.py`.

| Item | Where | Notes |
|---|---|---|
| `GCP_PROJECT_ID` | `secrets/.env` | Required. |
| `GCP_LOCATION` | `secrets/.env` | Where `setup_gcp` creates the bucket and datasets. Default `asia-southeast1`. Use one location for all of them. The `stylehub` course dataset may be elsewhere. |
| `GCS_BUCKET` | `secrets/.env` | Required. Bucket name only, with no `gs://`. |
| `GOOGLE_APPLICATION_CREDENTIALS` | `secrets/.env` | Path to the service account JSON, for example `secrets/gcp-sa.json`. A relative path is counted from the project folder. Never commit it. |
| `RAW_PREFIX` | `secrets/.env` | Folder for Raw files. Default `raw/stylehub`. |
| `BQ_SOURCE` | `secrets/.env` | Dataset with the course's original tables, such as `events`. Default `stylehub`. |
| `BQ_BRONZE`, `BQ_SILVER`, `BQ_GOLD` | `secrets/.env` | Dataset names. Defaults `stylehub_bronze`, `stylehub_silver`, `stylehub_gold`. |
| `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD` | `secrets/.env` (optional) | Only for the Postgres path. Never commit the password. |
| `PG_SSLMODE` | `secrets/.env` (optional) | `require` when the server demands TLS (the course server does). Default `prefer`. |
| `LOCAL_PG_PASSWORD` | Your shell (optional) | Password for the local Docker Postgres. Default `stylehub_local`. |
| `BQ_OPS` | `secrets/.env` | Dataset for `pipeline_runs`. Default `stylehub_ops`. Create it before the first run. |
| `ALERT_WEBHOOK_URL` | `secrets/.env` (optional) | Discord webhook for failure alerts. It is a secret. Leave it empty to turn alerts off. |
| Watermark column | `WATERMARK` in `src/python/ingestion/optional/database.py` | Postgres path only. The CSV path does not use it. |
| Lookback days | `LOOKBACK_DAYS` in `src/python/ingestion/optional/database.py` | Default 1. |
| Raw folder names | `RAW_DIR` in `src/python/common/config.py` | Needed when a folder name differs from the table name. Empty now. |

> [!WARNING]
> Never commit `secrets/` (it holds `.env` and the key file), GCP keys or passwords. `.gitignore` blocks them, but check `git status` before each commit.
