# Repository variables for the workflows; none of them is a secret.
output "github_variables" {
  description = "Set each one with: gh variable set NAME --body VALUE"
  value = {
    GCP_PROJECT_ID               = var.project_id
    GCP_REGION                   = var.region
    GCS_BUCKET                   = google_storage_bucket.raw.name
    AR_REPOSITORY                = google_artifact_registry_repository.images.repository_id
    TF_STATE_BUCKET              = var.state_bucket
    WIF_PROVIDER                 = google_iam_workload_identity_pool_provider.github_repo.name
    WIF_CD_SERVICE_ACCOUNT       = google_service_account.this["sa-github-cd"].email
    WIF_PLAN_SERVICE_ACCOUNT     = google_service_account.this["sa-terraform-plan"].email
    WIF_APPLY_SERVICE_ACCOUNT    = google_service_account.this["sa-terraform-apply"].email
    WIF_PIPELINE_SERVICE_ACCOUNT = google_service_account.this["sa-pipeline"].email
  }
}

output "service_accounts" {
  description = "Attach sa-pipeline to the Airflow VM and sa-dashboard to the dashboard."
  value       = { for name, account in google_service_account.this : name => account.email }
}

output "dashboard_url" {
  description = "Cloud Run dashboard; open it through: gcloud run services proxy stylehub-dashboard"
  value       = google_cloud_run_v2_service.dashboard.uri
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
