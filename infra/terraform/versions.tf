# Google Cloud resources of StyleHub; state lives in a GCS bucket.
terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Set once per machine: terraform init -backend-config="bucket=<state bucket>"
  backend "gcs" {
    prefix = "stylehub"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
