# Dev environment: its own datasets (suffix _dev) for trying dbt changes, built
# from the same module as prod. Shares the project, the course source dataset
# and the service accounts; state lives under its own prefix.
# Run: TF_ENV=dev TF_STATE_BUCKET=<bucket> infra/scripts/deploy.sh plan
terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    prefix = "stylehub-dev"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  layers = ["bronze", "staging", "silver", "gold", "ops"]
}

module "dataset" {
  source   = "../../modules/bigquery_dataset"
  for_each = toset(local.layers)

  dataset_id            = "stylehub_${each.key}_dev"
  location              = var.region
  table_expiration_days = var.table_expiration_days # dev data is temporary
  members = {
    for member in var.editors : member => { role = "roles/bigquery.dataEditor", member = member }
  }
}

output "dataset_ids" {
  description = "Put these in a dev .env as BQ_BRONZE, BQ_STAGING, BQ_SILVER, BQ_GOLD, BQ_OPS."
  value       = { for layer, dataset in module.dataset : layer => dataset.dataset_id }
}
