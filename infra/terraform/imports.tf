# Resources made before this config; delete this file after the first apply.
import {
  to = google_storage_bucket.raw
  id = var.bucket_name
}

import {
  for_each = var.datasets
  to       = google_bigquery_dataset.this[each.key]
  id       = "projects/${var.project_id}/datasets/${each.value}"
}

import {
  to = google_bigquery_table.pipeline_runs
  id = "projects/${var.project_id}/datasets/${var.datasets.ops}/tables/pipeline_runs"
}

import {
  to = google_artifact_registry_repository.images
  id = "projects/${var.project_id}/locations/${var.region}/repositories/${var.artifact_repository}"
}

import {
  to = google_iam_workload_identity_pool.github
  id = "projects/${var.project_id}/locations/global/workloadIdentityPools/github"
}

import {
  to = google_iam_workload_identity_pool_provider.github_repo
  id = "projects/${var.project_id}/locations/global/workloadIdentityPools/github/providers/github-repo"
}

import {
  to = google_service_account.this["sa-github-cd"]
  id = "projects/${var.project_id}/serviceAccounts/sa-github-cd@${var.project_id}.iam.gserviceaccount.com"
}
