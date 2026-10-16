locals {
  datasets = {
    source  = var.datasets.source # the course tables; ingestion reads them
    bronze  = var.datasets.bronze
    staging = var.datasets.staging # views that still hold personal data
    silver  = var.datasets.silver
    gold    = var.datasets.gold
    ops     = var.datasets.ops
  }
  # Dev copies that .github/workflows/dbt-ci.yaml writes (dbt target "dev", DBT_DEV_USER=ci).
  ci_datasets = var.enable_ci ? {
    ci_staging = "${var.ci_dataset_prefix}_stylehub_staging"
    ci_silver  = "${var.ci_dataset_prefix}_stylehub_silver"
    ci_gold    = "${var.ci_dataset_prefix}_stylehub_gold"
  } : {}
  all_datasets = merge(local.datasets, local.ci_datasets)
}

# ---- APIs --------------------------------------------------------------------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false # turning an API off can break other things in the project
}

# ---- Raw Zone bucket (same rules as src/stylehub/setup/setup_gcp.py) -----------------------------

resource "google_storage_bucket" "raw" {
  name                        = var.bucket_name
  location                    = coalesce(var.bucket_location, var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # Raw is the copy that Bronze is rebuilt from and there is no other backup.
  versioning {
    enabled = true
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

# ---- BigQuery datasets ---------------------------------------------------------------------------

resource "google_bigquery_dataset" "this" {
  for_each   = local.all_datasets
  dataset_id = each.value
  location   = each.key == "source" ? coalesce(var.source_location, var.region) : var.region

  # Staging holds personal data, so its tables expire. Other datasets keep what they have.
  default_table_expiration_ms = each.key == "staging" ? var.staging_table_expiration_days * 24 * 3600 * 1000 : null

  # A dataset that holds data is never deleted by Terraform.
  delete_contents_on_destroy = false

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.apis]
}

# ---- Docker images (see docs/ops/CD.md) ------------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  repository_id = var.artifact_repository
  location      = var.region
  format        = "DOCKER"
  description   = "StyleHub pipeline and Airflow images. Tags are commit ids."

  depends_on = [google_project_service.apis]
}
