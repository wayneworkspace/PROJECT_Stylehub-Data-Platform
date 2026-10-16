# Run the pipeline on a GCP VM

> [!NOTE]
> Airflow schedules the pipeline (see [deploy/airflow/README.md](../../deploy/airflow/README.md)). This page covers the VM, its service accounts and runs by hand. It does not set up a second schedule. The VM script is `deploy/pipeline/run_on_vm.sh`.

This page shows how to run the pipeline every day on small VMs. There is one VM per job, and each VM has its own service account attached. There are no key files.

> [!WARNING]
> I could not run these steps on a real GCP project. The script passes `bash -n`, but you are the first person to run these steps on a VM. Fix what breaks and update this page.

## The plan

| Job | Steps | Time (UTC) | Service account | Roles it needs |
|---|---|---|---|---|
| `stylehub-ingest` | ingest | 01:00 | `sa-ingest` | `storage.objectCreator` on the bucket. `bigquery.dataViewer` on the source dataset `stylehub` (it reads the CSV tables). `bigquery.dataEditor` on the `stylehub_ops` dataset and `bigquery.jobUser` on the project (to read the source and write `pipeline_runs`). |
| `stylehub-transform` | bronze, silver, gold | 01:30 | `sa-transform` | `storage.objectViewer` on the bucket. `bigquery.dataViewer` on `stylehub` (only for the one-time copy of `events`). `bigquery.dataEditor` on the bronze, staging, silver, gold and ops datasets. `bigquery.jobUser` on the project. |

Why two accounts: if the ingest VM is broken into, an attacker can add files to the Raw Zone and read the source tables, but cannot read or delete Raw files and cannot change any pipeline table. The transform account cannot write to the Raw Zone.

On your laptop one key is fine for learning (`secrets/`). On a VM there is no key at all: the account is attached to the VM, and the container gets short-lived tokens from the VM's metadata server. Nothing can be copied out and used later. `deploy/pipeline/run_on_vm.sh <from-step> <to-step>` takes only the two steps.

The data date is yesterday (UTC). Both VMs run the same Docker image.

## 1. Create the accounts and the VMs

Replace `PROJECT`, `REGION`, `BUCKET` and `YOUR_IP`. Use your own public IP, never `0.0.0.0/0`.

```bash
gcloud iam service-accounts create sa-ingest --project PROJECT
gcloud iam service-accounts create sa-transform --project PROJECT

gcloud storage buckets add-iam-policy-binding gs://BUCKET \
  --member serviceAccount:sa-ingest@PROJECT.iam.gserviceaccount.com --role roles/storage.objectCreator
gcloud storage buckets add-iam-policy-binding gs://BUCKET \
  --member serviceAccount:sa-transform@PROJECT.iam.gserviceaccount.com --role roles/storage.objectViewer
for sa in sa-ingest sa-transform; do
  gcloud projects add-iam-policy-binding PROJECT \
    --member serviceAccount:$sa@PROJECT.iam.gserviceaccount.com --role roles/bigquery.jobUser
  gcloud artifacts repositories add-iam-policy-binding stylehub --location=REGION --project PROJECT \
    --member serviceAccount:$sa@PROJECT.iam.gserviceaccount.com --role roles/artifactregistry.reader
done

# Keep old versions of Raw files, so a bad overwrite can be undone
gcloud storage buckets update gs://BUCKET --versioning
```

The Artifact Registry line is only needed if you use the image from [CD.md](CD.md).

Give `bigquery.dataEditor` on each dataset in the BigQuery console (dataset > Sharing > Permissions). Give `bigquery.dataViewer` on `stylehub` to both accounts. Create the `stylehub_ops` dataset first.

```bash
# One VM per job. The account is attached; cloud-platform scope lets IAM decide the rights.
gcloud compute instances create stylehub-ingest --project PROJECT --zone asia-southeast1-b \
  --machine-type e2-small --image-family debian-12 --image-project debian-cloud \
  --tags stylehub --service-account sa-ingest@PROJECT.iam.gserviceaccount.com --scopes cloud-platform
gcloud compute instances create stylehub-transform --project PROJECT --zone asia-southeast1-b \
  --machine-type e2-small --image-family debian-12 --image-project debian-cloud \
  --tags stylehub --service-account sa-transform@PROJECT.iam.gserviceaccount.com --scopes cloud-platform

gcloud compute firewall-rules create stylehub-ssh-mine --project PROJECT \
  --allow tcp:22 --source-ranges YOUR_IP/32 --target-tags stylehub
```

Each VM has exactly one Google identity, so a job on it cannot use the other job's rights.

## 2. Install Docker and the code

```bash
gcloud compute ssh stylehub-ingest --zone asia-southeast1-b   # then repeat on stylehub-transform
sudo apt-get update && sudo apt-get install -y docker.io git
sudo git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform /opt/stylehub
cd /opt/stylehub && sudo docker build -f deploy/pipeline/Dockerfile -t stylehub-pipeline .
```

To get the image from CD instead of building it here, follow [CD.md](CD.md) and skip the `docker build` line.

## 3. Add settings

Create `/etc/stylehub/pipeline.env` with the values from `.env.example`. Do not put quotes around values (Docker keeps them). Leave out `GOOGLE_APPLICATION_CREDENTIALS`: there is no key file, the VM account is used.

```bash
sudo mkdir -p /etc/stylehub && sudo chmod 700 /etc/stylehub
sudo chmod 600 /etc/stylehub/pipeline.env
```

## 4. Run a job by hand

Run a job by hand first, with a date you know:

```bash
sudo DATA_DATE=2026-10-01 /opt/stylehub/deploy/pipeline/run_on_vm.sh ingest ingest
```

Run it on the ingest VM. Without `DATA_DATE`, the script uses yesterday (UTC).

## 5. Read the logs

| Question | Command |
|---|---|
| Did the job run today? | `SELECT step, status, started_at FROM stylehub_ops.pipeline_runs ORDER BY started_at DESC LIMIT 10` |
| Which steps failed this week? | `SELECT * FROM stylehub_ops.pipeline_runs WHERE status = 'failed' ORDER BY started_at DESC` |

## Run it every day: Airflow only

Airflow is the ONE scheduler (`stylehub_daily`, 02:00 UTC). Do not add a cron line next to it: two
schedulers would run the same day twice, and cron cannot say "run bronze after ingest finished"
(a cron line at 01:30 only hopes that ingest ended by then). The DAG states that order.

`run_on_vm.sh` is for a run by hand: a retry of one step, or a first load while you set things up.

## Stop the cost

Stop the VMs when you are not using them: `gcloud compute instances stop stylehub-ingest stylehub-transform --zone asia-southeast1-b`. A stopped VM does not run any job.

## Did not run alert

Airflow cannot warn you when Airflow itself is down. `.github/workflows/freshness.yaml` checks from outside: every day at 06:00 UTC it runs `python -m stylehub.orchestration.check_freshness`, which reads `pipeline_runs` and sends a Discord message when the newest successful `gold` step is older than 26 hours (or there is none).

It uses a third service account that can only read the run history:

| Account | Roles it needs |
|---|---|
| `sa-monitor` | `bigquery.dataViewer` on the `stylehub_ops` and `stylehub_bronze` datasets (it also checks when Bronze was last loaded) and `bigquery.jobUser` on the project |

Set it up once (Workload Identity Federation, the same way as in [CD.md](CD.md)):

| Where | What to set |
|---|---|
| GitHub repository variables | `WIF_PROVIDER`, `WIF_MONITOR_SERVICE_ACCOUNT` (`sa-monitor@PROJECT.iam.gserviceaccount.com`), `GCP_PROJECT_ID`, `GCS_BUCKET` |
| GitHub repository secret | `ALERT_WEBHOOK_URL` |

The job is skipped until `WIF_MONITOR_SERVICE_ACCOUNT` is set. Test it by hand from the Actions tab (`Run workflow`), or on your laptop: `uv run python -m stylehub.orchestration.check_freshness --max-age-hours 1`.

> [!WARNING]
> I could not run this workflow. GitHub also turns off scheduled workflows after 60 days without activity in the repository.
