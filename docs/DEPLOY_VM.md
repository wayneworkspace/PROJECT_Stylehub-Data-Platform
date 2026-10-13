# Run the pipeline on a GCP VM

This page shows how to run the pipeline every day on a small VM, with two service accounts that each do one job.

> [!WARNING]
> I could not run these steps on a real GCP project. The unit files pass `systemd-analyze` and the script passes `bash -n`, but you are the first person to run them on a VM. Fix what breaks and update this page.

## The plan

| Job | Steps | Time (UTC) | Service account | Roles it needs |
|---|---|---|---|---|
| `stylehub-ingest` | ingest | 01:00 | `sa-ingest` | `storage.objectCreator` on the bucket. `bigquery.dataEditor` on the `stylehub_ops` dataset and `bigquery.jobUser` on the project (only to write `pipeline_runs`). |
| `stylehub-transform` | bronze, silver, gold, checks | 01:30 | `sa-transform` | `storage.objectViewer` on the bucket. `bigquery.dataEditor` on the bronze, silver, gold and ops datasets. `bigquery.jobUser` on the project. |

Why two accounts: if the ingest key leaks, an attacker can add files to the Raw Zone but cannot read or delete data, and cannot touch BigQuery tables.

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

Give `bigquery.dataEditor` on each dataset in the BigQuery console (dataset > Sharing > Permissions). Create the `stylehub_ops` dataset first.

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
cd /opt/stylehub && sudo docker build -t stylehub-pipeline .
```

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
sudo DATA_DATE=2026-10-01 /opt/stylehub/deploy/run_pipeline.sh ingest ingest /etc/stylehub/ingest-sa.json
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
0 1 * * *  /opt/stylehub/deploy/run_pipeline.sh ingest ingest /etc/stylehub/ingest-sa.json
30 1 * * * /opt/stylehub/deploy/run_pipeline.sh bronze checks /etc/stylehub/transform-sa.json
```

## Stop the cost

Stop the VM when you are not using it: `gcloud compute instances stop stylehub-vm --zone asia-southeast1-b`. A stopped VM does not run the timers.
