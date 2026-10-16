# GitHub Actions signs in with Workload Identity Federation: a short-lived token, no JSON key in
# GitHub. Only the repository in var.github_repository may use it (the attribute condition).

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github_repo" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-repo"
  display_name                       = "GitHub repository"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  github_principal = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
  github_accounts  = toset(concat(["sa-github-cd", "sa-monitor"], var.enable_ci ? ["sa-dbt-ci"] : []))
}

resource "google_service_account_iam_member" "github_may_use" {
  for_each           = local.github_accounts
  service_account_id = google_service_account.this[each.value].name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.github_principal
}
