resource "google_project_service" "apis" {
  for_each = toset([
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "compute.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false # turning an API off can break other things
}

# Raw Zone: append-only Parquet, the copy Bronze is rebuilt from.
resource "google_storage_bucket" "raw" {
  name                        = var.bucket_name
  location                    = coalesce(var.bucket_location, var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true # restores files overwritten or deleted by mistake
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = var.noncurrent_retention_days
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = var.raw_retention_days
      matches_prefix = ["${var.raw_prefix}/"]
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.apis]
}

module "dataset" {
  source   = "./modules/bigquery_dataset"
  for_each = var.datasets

  dataset_id            = each.value
  location              = each.key == "source" ? coalesce(var.source_location, var.region) : var.region
  table_expiration_days = each.key == "staging" ? var.staging_table_expiration_days : null
  # Data rights sit on datasets (iam.tf, local.dataset_access).
  members = {
    for name, access in local.dataset_access : name => { role = access.role, member = local.sa[access.sa] }
    if access.dataset == each.key
  }

  depends_on = [google_project_service.apis]
}

# One row per pipeline step per run; written by src/3_storage/runs.py.
resource "google_bigquery_table" "pipeline_runs" {
  dataset_id          = module.dataset["ops"].dataset_id
  table_id            = "pipeline_runs"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "started_at"
  }

  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED" },
    { name = "step", type = "STRING", mode = "REQUIRED" },
    { name = "data_date", type = "DATE", mode = "REQUIRED" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "success or failed" },
    { name = "started_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "finished_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "duration_seconds", type = "FLOAT", mode = "NULLABLE" },
    { name = "rows_loaded", type = "INTEGER", mode = "NULLABLE" },
    { name = "error", type = "STRING", mode = "NULLABLE" },
    { name = "detail", type = "STRING", mode = "NULLABLE", description = "JSON: rows per table, dbt counts" },
  ])
}

resource "google_artifact_registry_repository" "images" {
  repository_id = var.artifact_repository
  location      = var.region
  format        = "DOCKER"
  description   = "StyleHub Airflow and dashboard images; tags are commit ids."

  depends_on = [google_project_service.apis]
}
