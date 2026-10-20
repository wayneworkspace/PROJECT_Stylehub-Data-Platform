# Monthly budget for this personal project: e-mails at 50%, 90% and 100% of
# var.budget_usd, so a free-tier mistake shows up the same day.
# Needs once, by a billing account admin (Terraform cannot grant itself this):
#   gcloud billing accounts add-iam-policy-binding <BILLING_ACCOUNT_ID> \
#     --member=serviceAccount:<sa-terraform-apply e-mail> --role=roles/billing.costsManager
# then set the GitHub variable BILLING_ACCOUNT_ID.
data "google_project" "this" {
  project_id = var.project_id
}

resource "google_billing_budget" "monthly" {
  count           = var.billing_account_id == "" ? 0 : 1
  billing_account = var.billing_account_id
  display_name    = "StyleHub monthly budget"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.apis]
}
