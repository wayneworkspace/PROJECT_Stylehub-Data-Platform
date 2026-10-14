# Run the pipeline on a GCP VM

> [!NOTE]
> The systemd timers described here were removed from the repo. Airflow now schedules the pipeline (see [deploy/airflow/README.md](../../deploy/airflow/README.md)). Keep this page only as a starting point for a VM setup, and expect to adapt it. `deploy/pipeline/run_on_vm.sh` is still there.

This page shows how to run the pipeline every day on a small VM, with two service accounts that each do one job.

> [!WARNING]
> I could not run these steps on a real GCP project. The unit files pass `systemd-analyze` and the script passes `bash -n`, but you are the first person to run them on a VM. Fix what breaks and update this page.

## The plan

| Job | Steps | Time (UTC) | Service account | Roles it needs |
|---|---|---|---|---|
| `stylehub-ingest` | ingest | 01:00 | `sa-ingest` | `storage.objectCreator` on the bucket. `bigquery.dataViewer` on the source dataset `stylehub` (it reads the CSV tables). `bigquery.dataEditor` on the `stylehub_ops` dataset and `bigquery.jobUser` on the project (to read the source and write `pipeline_runs`). |
| `stylehub-transform` | bronze, silver, gold | 01:30 | `sa-transform` | `storage.objectViewer` on the bucket. `bigquery.dataViewer` on `stylehub` (only for the one-time copy of `events`). `bigquery.dataEditor` on the bronze, silver, gold and ops datasets. `bigquery.jobUser` on the project. |

Why two accounts: if the ingest key leaks, an attacker can add files to the Raw Zone and read the source tables, but cannot read or delete Raw files and cannot change any pipeline table. The transform key cannot write to the Raw Zone.

On your laptop one key is fine for learning (`secrets/`). The split is for the VM and for Airflow, where each job gets its own key. `deploy/pipeline/run_on_vm.sh` already takes the key file as its third argument, so each job passes its own.

The data date is yesterday (UTC). Both jobs run from the same Docker image.

## 1. Create the accounts and the VM

Replace `PROJECT`, `BUCKET` and `YOUR_IP`. Use your own public IP, never `0.0.0.0/0`.

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
done
```

Give `bigquery.dataEditor` on each dataset in the BigQuery console (dataset > Sharing > Permissions). Give `bigquery.dataViewer` on `stylehub` to both accounts. Create the `stylehub_ops` dataset first.

```bash
gcloud compute instances create stylehub-vm --project PROJECT --zone asia-southeast1-b \
  --machine-type e2-small --image-family debian-12 --image-project debian-cloud \
  --tags stylehub --no-service-account --no-scopes

gcloud compute firewall-rules create stylehub-ssh-mine --project PROJECT \
  --allow tcp:22 --source-ranges YOUR_IP/32 --target-tags stylehub
```

`--no-service-account` means the VM itself has no Google identity. Only the two key files below give access.

## 2. Install Docker and the code

```bash
gcloud compute ssh stylehub-vm --zone asia-southeast1-b
sudo apt-get update && sudo apt-get install -y docker.io git
sudo git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform /opt/stylehub
cd /opt/stylehub && sudo docker build -f deploy/pipeline/Dockerfile -t stylehub-pipeline .
```

To get the image from CD instead of building it here, follow [CD.md](CD.md) and skip the `docker build` line.

## 3. Add settings and keys

Create `/etc/stylehub/pipeline.env` with the values from `.env.example`. Do not put quotes around values (Docker keeps them). Leave out `GOOGLE_APPLICATION_CREDENTIALS`: the script sets it.

Create one key per account (on your own computer, then copy them over). Keep them out of Git.

```bash
sudo mkdir -p /etc/stylehub && sudo chmod 700 /etc/stylehub
# copy ingest-sa.json and transform-sa.json here, then:
sudo chmod 444 /etc/stylehub/*-sa.json
sudo chmod 600 /etc/stylehub/pipeline.env
```

The folder is root-only, so the file mode `444` is safe.

## 4. Turn on the timers

```bash
sudo cp /opt/stylehub/deploy/stylehub-*.service /opt/stylehub/deploy/stylehub-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stylehub-ingest.timer stylehub-transform.timer
systemctl list-timers 'stylehub-*'
```

Run a job by hand first, with a date you know:

```bash
sudo DATA_DATE=2026-10-01 /opt/stylehub/deploy/pipeline/run_on_vm.sh ingest ingest /etc/stylehub/ingest-sa.json
```

`systemctl start stylehub-ingest` also works, but it always uses yesterday.

## 5. Read the logs

| Question | Command |
|---|---|
| What did the last ingest print? | `journalctl -u stylehub-ingest -n 100 --no-pager` |
| Did the job run today? | `systemctl status stylehub-ingest.service` |
| When is the next run? | `systemctl list-timers 'stylehub-*'` |
| Which steps failed this week? | `SELECT * FROM stylehub_ops.pipeline_runs WHERE status = 'failed' ORDER BY started_at DESC` |

## Same thing with cron

If you prefer cron, add this to `sudo crontab -e`. It does the same work, but you lose `journalctl` and the catch-up after a reboot (`Persistent=true`).

```cron
0 1 * * *  /opt/stylehub/deploy/pipeline/run_on_vm.sh ingest ingest /etc/stylehub/ingest-sa.json
30 1 * * * /opt/stylehub/deploy/pipeline/run_on_vm.sh bronze checks /etc/stylehub/transform-sa.json
```

## Stop the cost

Stop the VM when you are not using it: `gcloud compute instances stop stylehub-vm --zone asia-southeast1-b`. A stopped VM does not run the timers.

## Did not run alert

Airflow cannot warn you when Airflow itself is down. `.github/workflows/freshness.yaml` checks from outside: every day at 06:00 UTC it runs `python -m orchestration.check_freshness`, which reads `pipeline_runs` and sends a Discord message when the newest successful `gold` step is older than 26 hours (or there is none).

It uses a third service account that can only read the run history:

| Account | Roles it needs |
|---|---|
| `sa-monitor` | `bigquery.dataViewer` on the `stylehub_ops` dataset and `bigquery.jobUser` on the project |

Set it up once (Workload Identity Federation, the same way as in [CD.md](CD.md)):

| Where | What to set |
|---|---|
| GitHub repository variables | `WIF_PROVIDER`, `WIF_MONITOR_SERVICE_ACCOUNT` (`sa-monitor@PROJECT.iam.gserviceaccount.com`), `GCP_PROJECT_ID`, `GCS_BUCKET` |
| GitHub repository secret | `ALERT_WEBHOOK_URL` |

The job is skipped until `WIF_MONITOR_SERVICE_ACCOUNT` is set. Test it by hand from the Actions tab (`Run workflow`), or on your laptop: `uv run python -m orchestration.check_freshness --max-age-hours 1`.

> [!WARNING]
> I could not run this workflow. GitHub also turns off scheduled workflows after 60 days without activity in the repository.
