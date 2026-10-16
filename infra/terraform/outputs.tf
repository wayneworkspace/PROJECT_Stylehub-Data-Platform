# The values that GitHub needs. Set them as repository VARIABLES (none of them is a secret):
#   terraform output -json github_variables
# docs/ops/TERRAFORM.md has a PowerShell loop that runs `gh variable set` for each one.
output "github_variables" {
  description = "Repository variables for ci.yaml, cd.yaml, dbt-ci.yaml and freshness.yaml."
  value = merge(
    {
      GCP_PROJECT_ID              = var.project_id
      GCP_REGION                  = var.region
      GCS_BUCKET                  = google_storage_bucket.raw.name
      AR_REPOSITORY               = google_artifact_registry_repository.images.repository_id
      WIF_PROVIDER                = google_iam_workload_identity_pool_provider.github_repo.name
      WIF_SERVICE_ACCOUNT         = google_service_account.this["sa-github-cd"].email
      WIF_MONITOR_SERVICE_ACCOUNT = google_service_account.this["sa-monitor"].email
    },
    var.enable_ci ? { WIF_CI_SERVICE_ACCOUNT = google_service_account.this["sa-dbt-ci"].email } : {}
  )
}

output "service_accounts" {
  description = "Attach sa-ingest and sa-transform to the VMs (--service-account)."
  value       = { for name, account in google_service_account.this : name => account.email }
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
