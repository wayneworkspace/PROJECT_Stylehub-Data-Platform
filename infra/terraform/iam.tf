# One service account per job, least privilege, no key files.
locals {
  service_accounts = {
    "sa-pipeline"        = "Airflow pipeline and dbt in CD: Raw, Bronze, Silver, Gold"
    "sa-dashboard"       = "Streamlit dashboard: read only"
    "sa-github-cd"       = "GitHub CD: pushes images"
    "sa-terraform-plan"  = "GitHub CI: terraform plan, read only"
    "sa-terraform-apply" = "GitHub CD on main: terraform apply"
  }
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

  # Data rights sit on datasets; the project only grants starting a job.
  dataset_access = {
    "pipeline-source-viewer"  = { dataset = "source", role = "roles/bigquery.dataViewer", sa = "sa-pipeline" }
    "pipeline-bronze-editor"  = { dataset = "bronze", role = "roles/bigquery.dataEditor", sa = "sa-pipeline" }
    "pipeline-staging-editor" = { dataset = "staging", role = "roles/bigquery.dataEditor", sa = "sa-pipeline" }
    "pipeline-silver-editor"  = { dataset = "silver", role = "roles/bigquery.dataEditor", sa = "sa-pipeline" }
    "pipeline-gold-editor"    = { dataset = "gold", role = "roles/bigquery.dataEditor", sa = "sa-pipeline" }
    "pipeline-ops-editor"     = { dataset = "ops", role = "roles/bigquery.dataEditor", sa = "sa-pipeline" }
    "dashboard-ops-viewer"    = { dataset = "ops", role = "roles/bigquery.dataViewer", sa = "sa-dashboard" }
    "dashboard-bronze-viewer" = { dataset = "bronze", role = "roles/bigquery.dataViewer", sa = "sa-dashboard" }
    "dashboard-silver-viewer" = { dataset = "silver", role = "roles/bigquery.dataViewer", sa = "sa-dashboard" }
  }

  project_roles = {
    "pipeline-job-user"  = { role = "roles/bigquery.jobUser", sa = "sa-pipeline" }
    "dashboard-job-user" = { role = "roles/bigquery.jobUser", sa = "sa-dashboard" }
    # Plan reads metadata and IAM policies only, never table rows or files.
    "plan-iam-reader"   = { role = "roles/iam.securityReviewer", sa = "sa-terraform-plan" }
    "plan-apis"         = { role = "roles/serviceusage.serviceUsageViewer", sa = "sa-terraform-plan" }
    "plan-bigquery"     = { role = "roles/bigquery.metadataViewer", sa = "sa-terraform-plan" }
    "plan-buckets"      = { role = "roles/storage.bucketViewer", sa = "sa-terraform-plan" }
    "plan-accounts"     = { role = "roles/iam.serviceAccountViewer", sa = "sa-terraform-plan" }
    "plan-wif"          = { role = "roles/iam.workloadIdentityPoolViewer", sa = "sa-terraform-plan" }
    "plan-registry"     = { role = "roles/artifactregistry.reader", sa = "sa-terraform-plan" }
    "plan-log-metrics"  = { role = "roles/logging.viewer", sa = "sa-terraform-plan" }
    "plan-alerts"       = { role = "roles/monitoring.alertPolicyViewer", sa = "sa-terraform-plan" }
    "plan-secrets"      = { role = "roles/secretmanager.viewer", sa = "sa-terraform-plan" }
    "plan-compute"      = { role = "roles/compute.viewer", sa = "sa-terraform-plan" }
    "apply-storage"     = { role = "roles/storage.admin", sa = "sa-terraform-apply" }
    "apply-bigquery"    = { role = "roles/bigquery.admin", sa = "sa-terraform-apply" }
    "apply-registry"    = { role = "roles/artifactregistry.admin", sa = "sa-terraform-apply" }
    "apply-accounts"    = { role = "roles/iam.serviceAccountAdmin", sa = "sa-terraform-apply" }
    "apply-wif"         = { role = "roles/iam.workloadIdentityPoolAdmin", sa = "sa-terraform-apply" }
    "apply-project-iam" = { role = "roles/resourcemanager.projectIamAdmin", sa = "sa-terraform-apply" }
    "apply-apis"        = { role = "roles/serviceusage.serviceUsageAdmin", sa = "sa-terraform-apply" }
    "apply-log-metrics" = { role = "roles/logging.configWriter", sa = "sa-terraform-apply" }
    "apply-alerts"      = { role = "roles/monitoring.alertPolicyEditor", sa = "sa-terraform-apply" }
    "apply-secrets"     = { role = "roles/secretmanager.admin", sa = "sa-terraform-apply" }
    "apply-compute"     = { role = "roles/compute.instanceAdmin.v1", sa = "sa-terraform-apply" }
    "apply-firewall"    = { role = "roles/compute.securityAdmin", sa = "sa-terraform-apply" }
  }
}

resource "google_project_iam_member" "this" {
  for_each = local.project_roles
  project  = var.project_id
  role     = each.value.role
  member   = local.sa[each.value.sa]
}

# Raw Zone: the pipeline may add and read files, never overwrite or delete.
resource "google_storage_bucket_iam_member" "pipeline_raw" {
  for_each = toset(["roles/storage.objectCreator", "roles/storage.objectViewer"])
  bucket   = google_storage_bucket.raw.name
  role     = each.value
  member   = local.sa["sa-pipeline"]
}

# Plan takes the state lock, so it writes lock files in the state bucket.
resource "google_storage_bucket_iam_member" "plan_state" {
  bucket = var.state_bucket
  role   = "roles/storage.objectUser"
  member = local.sa["sa-terraform-plan"]
}

resource "google_artifact_registry_repository_iam_member" "cd_writes" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = local.sa["sa-github-cd"]
}

resource "google_artifact_registry_repository_iam_member" "runtime_reads" {
  for_each   = toset(["sa-pipeline", "sa-dashboard"])
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.reader"
  member     = local.sa[each.value]
}

# Apply may attach sa-pipeline to the Airflow VM, and no other account.
resource "google_service_account_iam_member" "apply_uses_pipeline" {
  service_account_id = google_service_account.this["sa-pipeline"].name
  role               = "roles/iam.serviceAccountUser"
  member             = local.sa["sa-terraform-apply"]
}
