# Terraform describes the Google Cloud pieces of StyleHub: bucket, datasets, service accounts and
# the login for GitHub Actions. Run it from this folder (see docs/ops/TERRAFORM.md).
terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # State is kept in a local file (terraform.tfstate) that Git ignores. For a team, move it to a
  # bucket that is NOT the Raw Zone bucket:
  #   backend "gcs" { bucket = "my-tfstate-bucket", prefix = "stylehub" }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
