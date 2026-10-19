# Secret Manager holds the whole secrets/.env of a server (database URL,
# webhook, Airflow passwords). Terraform makes the empty secret; the value is
# added by hand, so it never lands in Terraform state:
#   gcloud secrets versions add stylehub-dotenv --data-file=secrets/.env.vm
resource "google_secret_manager_secret" "dotenv" {
  secret_id = "stylehub-dotenv"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# Only the pipeline account (the VM) may read the value.
resource "google_secret_manager_secret_iam_member" "pipeline_reads_dotenv" {
  secret_id = google_secret_manager_secret.dotenv.id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.sa["sa-pipeline"]
}
