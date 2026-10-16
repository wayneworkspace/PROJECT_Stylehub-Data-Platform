# One service account per job, least privilege (docs/ops/DEPLOY_VM.md). No key files are made.

locals {
  service_accounts = merge(
    {
      "sa-ingest"    = "Ingest job: reads the course tables, writes the Raw Zone"
      "sa-transform" = "Transform job: Bronze, Silver and Gold"
      "sa-monitor"   = "Freshness check: reads the run history only"
      "sa-github-cd" = "GitHub Actions CD: pushes images"
    },
    var.enable_ci ? { "sa-dbt-ci" = "GitHub Actions: dbt build in the dev datasets" } : {}
  )
}

resource "google_service_account" "this" {
  for_each     = local.service_accounts
  account_id   = each.key
  display_name = each.key
  description  = each.value

  depends_on = [google_project_service.apis]
}

locals {
  sa = { for name, account in google_service_account.this : name => "serviceAccount:${account.email}" }

  # Project level: only the right to START a query job (the data rights are on the datasets).
  # Account NAMES are the keys (known at plan time); the emails are only read as values.
  job_users = toset(concat(["sa-ingest", "sa-transform", "sa-monitor"], var.enable_ci ? ["sa-dbt-ci"] : []))

  # { "<label>" = { dataset = <layer>, role = ..., member = ... } }
  dataset_access = merge(
    {
      "ingest-source-viewer"     = { dataset = "source", role = "roles/bigquery.dataViewer", member = local.sa["sa-ingest"] }
      "ingest-ops-editor"        = { dataset = "ops", role = "roles/bigquery.dataEditor", member = local.sa["sa-ingest"] }
      "transform-source-viewer"  = { dataset = "source", role = "roles/bigquery.dataViewer", member = local.sa["sa-transform"] } # one-time copy of events
      "transform-bronze-editor"  = { dataset = "bronze", role = "roles/bigquery.dataEditor", member = local.sa["sa-transform"] }
      "transform-staging-editor" = { dataset = "staging", role = "roles/bigquery.dataEditor", member = local.sa["sa-transform"] }
      "transform-silver-editor"  = { dataset = "silver", role = "roles/bigquery.dataEditor", member = local.sa["sa-transform"] }
      "transform-gold-editor"    = { dataset = "gold", role = "roles/bigquery.dataEditor", member = local.sa["sa-transform"] }
      "transform-ops-editor"     = { dataset = "ops", role = "roles/bigquery.dataEditor", member = local.sa["sa-transform"] }
      "monitor-ops-viewer"       = { dataset = "ops", role = "roles/bigquery.dataViewer", member = local.sa["sa-monitor"] }
      "monitor-bronze-viewer"    = { dataset = "bronze", role = "roles/bigquery.dataViewer", member = local.sa["sa-monitor"] }
    },
    var.enable_ci ? {
      "ci-bronze-viewer"      = { dataset = "bronze", role = "roles/bigquery.dataViewer", member = local.sa["sa-dbt-ci"] }
      "ci-dev-staging-editor" = { dataset = "ci_staging", role = "roles/bigquery.dataEditor", member = local.sa["sa-dbt-ci"] }
      "ci-dev-silver-editor"  = { dataset = "ci_silver", role = "roles/bigquery.dataEditor", member = local.sa["sa-dbt-ci"] }
      "ci-dev-gold-editor"    = { dataset = "ci_gold", role = "roles/bigquery.dataEditor", member = local.sa["sa-dbt-ci"] }
    } : {}
  )
}

resource "google_project_iam_member" "job_user" {
  for_each = local.job_users
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = local.sa[each.value]
}

resource "google_bigquery_dataset_iam_member" "access" {
  for_each   = local.dataset_access
  dataset_id = google_bigquery_dataset.this[each.value.dataset].dataset_id
  role       = each.value.role
  member     = each.value.member
}

# ---- Raw Zone bucket -------------------------------------------------------------------------------

resource "google_storage_bucket_iam_member" "ingest_writes_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectCreator" # may add files, may not overwrite or delete (append-only)
  member = local.sa["sa-ingest"]
}

resource "google_storage_bucket_iam_member" "transform_reads_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectViewer"
  member = local.sa["sa-transform"]
}

# ---- Images ----------------------------------------------------------------------------------------

resource "google_artifact_registry_repository_iam_member" "cd_writes" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = local.sa["sa-github-cd"]
}

resource "google_artifact_registry_repository_iam_member" "vms_read" {
  for_each   = toset(["sa-ingest", "sa-transform"])
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.reader"
  member     = local.sa[each.value]
}
