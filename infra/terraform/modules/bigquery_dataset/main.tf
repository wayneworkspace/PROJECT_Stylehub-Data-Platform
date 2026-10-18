# One BigQuery dataset plus its dataset-level IAM members.
# Used by the prod root (infra/terraform) and the dev root (envs/dev).
resource "google_bigquery_dataset" "this" {
  dataset_id                  = var.dataset_id
  location                    = var.location
  default_table_expiration_ms = var.table_expiration_days == null ? null : var.table_expiration_days * 24 * 3600 * 1000
  delete_contents_on_destroy  = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_bigquery_dataset_iam_member" "this" {
  for_each   = var.members
  dataset_id = google_bigquery_dataset.this.dataset_id
  role       = each.value.role
  member     = each.value.member
}
