# Datasets and their IAM moved into modules/bigquery_dataset; these blocks
# rename state entries so nothing is destroyed. Delete them after one apply.

moved {
  from = google_bigquery_dataset.this["source"]
  to   = module.dataset["source"].google_bigquery_dataset.this
}

moved {
  from = google_bigquery_dataset.this["bronze"]
  to   = module.dataset["bronze"].google_bigquery_dataset.this
}

moved {
  from = google_bigquery_dataset.this["staging"]
  to   = module.dataset["staging"].google_bigquery_dataset.this
}

moved {
  from = google_bigquery_dataset.this["silver"]
  to   = module.dataset["silver"].google_bigquery_dataset.this
}

moved {
  from = google_bigquery_dataset.this["gold"]
  to   = module.dataset["gold"].google_bigquery_dataset.this
}

moved {
  from = google_bigquery_dataset.this["ops"]
  to   = module.dataset["ops"].google_bigquery_dataset.this
}

moved {
  from = google_bigquery_dataset_iam_member.this["pipeline-source-viewer"]
  to   = module.dataset["source"].google_bigquery_dataset_iam_member.this["pipeline-source-viewer"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["pipeline-bronze-editor"]
  to   = module.dataset["bronze"].google_bigquery_dataset_iam_member.this["pipeline-bronze-editor"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["pipeline-staging-editor"]
  to   = module.dataset["staging"].google_bigquery_dataset_iam_member.this["pipeline-staging-editor"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["pipeline-silver-editor"]
  to   = module.dataset["silver"].google_bigquery_dataset_iam_member.this["pipeline-silver-editor"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["pipeline-gold-editor"]
  to   = module.dataset["gold"].google_bigquery_dataset_iam_member.this["pipeline-gold-editor"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["pipeline-ops-editor"]
  to   = module.dataset["ops"].google_bigquery_dataset_iam_member.this["pipeline-ops-editor"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["dashboard-ops-viewer"]
  to   = module.dataset["ops"].google_bigquery_dataset_iam_member.this["dashboard-ops-viewer"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["dashboard-bronze-viewer"]
  to   = module.dataset["bronze"].google_bigquery_dataset_iam_member.this["dashboard-bronze-viewer"]
}

moved {
  from = google_bigquery_dataset_iam_member.this["dashboard-silver-viewer"]
  to   = module.dataset["silver"].google_bigquery_dataset_iam_member.this["dashboard-silver-viewer"]
}
