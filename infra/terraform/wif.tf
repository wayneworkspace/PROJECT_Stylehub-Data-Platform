# GitHub Actions signs in with a short-lived token; no JSON key in GitHub.
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
    # "yes" only for runs on main, so apply rights never reach pull requests.
    "attribute.main" = "assertion.ref == 'refs/heads/main' ? 'yes' : 'no'"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  pool        = google_iam_workload_identity_pool.github.name
  any_branch  = "principalSet://iam.googleapis.com/${local.pool}/attribute.repository/${var.github_repository}"
  main_branch = "principalSet://iam.googleapis.com/${local.pool}/attribute.main/yes"

  github_access = {
    "sa-terraform-plan"  = local.any_branch
    "sa-terraform-apply" = local.main_branch
    "sa-github-cd"       = local.main_branch
    "sa-pipeline"        = local.main_branch # dbt run in CD
  }
}

resource "google_service_account_iam_member" "github" {
  for_each           = local.github_access
  service_account_id = google_service_account.this[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value
}
