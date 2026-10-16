# Terraform

> **Run once, on 2026-10-16**, against the real project: `plan` (0 to destroy), `apply` (11 imported,
> 39 added, 5 changed) and a second `plan` (no changes). It has not been tried on a project that is
> empty. See "What the first run found" at the end.

Terraform describes the Google Cloud setup of StyleHub as code, in `infra/terraform/`:

| File | What it makes |
|---|---|
| `main.tf` | The APIs, the Raw Zone bucket (versioning, delete rules, no public access), the BigQuery datasets, the image repository |
| `iam.tf` | One service account per job and the least-privilege roles of [DEPLOY_VM.md](DEPLOY_VM.md) |
| `wif.tf` | The login for GitHub Actions (Workload Identity Federation), for your repository only |
| `outputs.tf` | The values that GitHub needs, as one JSON |

It does **not** make the VMs, the firewall or the `pipeline_runs` table (`setup_gcp` makes that
table). It makes no key files.

## Why

The same setup is typed by hand in [CD.md](CD.md) and [DEPLOY_VM.md](DEPLOY_VM.md). By hand, nobody
can see what changed or what drifted. With Terraform, `plan` shows the difference before anything
happens, and the roles are written in one place that a reviewer can read.

## Before you start

Terraform asks for your Google login, not a key file.

```powershell
winget install Hashicorp.Terraform
gcloud auth application-default login
gcloud auth application-default set-quota-project <PROJECT_ID>
cd infra\terraform
Copy-Item terraform.tfvars.example terraform.tfvars   # then fill in the three values
```

`gcloud auth application-default login` is only for Terraform. To use the `gcloud` and `bq` commands too, run `gcloud auth login`.

Git ignores `terraform.tfvars` and the state file (`terraform.tfstate`). The state holds resource
ids, so never commit it.

## Run it

```powershell
terraform init
terraform fmt              # fixes the spacing; the first run will change some lines
terraform validate         # checks the files without touching Google Cloud
terraform plan -out tfplan
```

Read the plan. For a project that already exists, it will try to **create** things that are
already there. Adopt them first:

```powershell
Copy-Item imports.tf.example imports.tf
terraform plan -out tfplan
```

Delete the blocks of things that do not exist yet in `imports.tf`, or `plan` stops with "Cannot
import non-existent remote object". The `plan` should then say **0 to destroy**. If it says
anything else, stop and read it. Then:

```powershell
terraform apply tfplan
Remove-Item imports.tf     # the import is done
```

`prevent_destroy` is on for the bucket and the datasets, so Terraform refuses to delete them even
if you ask. Removing them takes an edit in the files on purpose.

## Give the values to GitHub

```powershell
terraform output -json github_variables | ConvertFrom-Json | ForEach-Object {
  $_.PSObject.Properties | ForEach-Object { gh variable set $_.Name --body $_.Value }
}
```

This sets `GCP_PROJECT_ID`, `GCP_REGION`, `GCS_BUCKET`, `AR_REPOSITORY`, `WIF_PROVIDER`,
`WIF_SERVICE_ACCOUNT`, `WIF_MONITOR_SERVICE_ACCOUNT` and `WIF_CI_SERVICE_ACCOUNT`. The last one
turns on `.github/workflows/dbt-ci.yaml`, which then runs the models, tests and unit tests on
BigQuery in the `dbt_ci_*` datasets. None of these values is a secret.

Attach `sa-ingest` and `sa-transform` to the VMs with `terraform output service_accounts`.

## What to check

| Check | How |
|---|---|
| The files are valid | `terraform validate` prints "Success" |
| Nothing is deleted | `terraform plan` says "0 to destroy" |
| The roles are the right ones | Compare the table in [DEPLOY_VM.md](DEPLOY_VM.md) with `iam.tf` |
| GitHub can sign in | Run the `dbt build` workflow from the Actions tab |

## Limits

| Area | Limit |
|---|---|
| One project | It ran once, on one project that already had a bucket, datasets and one service account. A fresh project was not tried (there you skip `imports.tf`) |
| State | A local file, `terraform.tfstate`. Copy it to a safe place outside the repo: if it is lost, Terraform forgets what it made. For a team, use a `gcs` backend in a separate bucket (a comment in `versions.tf` shows how) |
| CI | CI does not check these files. Run `terraform fmt -check` and `terraform validate` by hand before you commit |
| Delete rules | The bucket rules delete Raw files after 90 days. They are the same as in `setup_gcp.py`, so applying them changes nothing if `setup_gcp` already ran |
| Old way | `setup_gcp` still works. Use one of the two for the bucket and datasets, not both with different settings |

## What the first run found

| Finding | What it means |
|---|---|
| `account_id` must have 6 to 30 characters | `sa-ci` was too short. It is now `sa-dbt-ci`. `validate` does not see this, only `plan` does |
| A bucket or dataset cannot change its location | The bucket was in `ASIA` and the source dataset `stylehub` in `US`, the others in `asia-southeast1`. Set `bucket_location` and `source_location` in `terraform.tfvars` to what you really have |
| The staging dataset already deleted tables after 7 days | `staging_table_expiration_days` (7) keeps it. Without it, Terraform would have removed the rule |
| The import showed only small changes | Names and descriptions were added, the repository condition got spaces, and bucket versioning was turned on. The bucket delete rules were already the same |
