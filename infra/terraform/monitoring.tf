# Alert when a pipeline account's BigQuery job fails, even outside Airflow
# (for example dbt in CD). Discord cannot read Monitoring's webhook format,
# so Airflow posts to Discord and this alert shows in Cloud Monitoring.
locals {
  pipeline_principals = "^(sa-pipeline|end2endstylehub)@"
}

resource "google_logging_metric" "bigquery_job_errors" {
  name   = "stylehub/bigquery_job_errors"
  filter = <<-EOT
    protoPayload.serviceName="bigquery.googleapis.com"
    protoPayload.metadata.jobChange.after="DONE"
    protoPayload.metadata.jobChange.job.jobStatus.errorResult.code:*
    protoPayload.authenticationInfo.principalEmail=~"${local.pipeline_principals}"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }

  depends_on = [google_project_service.apis, google_project_iam_member.this]
}

resource "google_monitoring_alert_policy" "bigquery_job_errors" {
  display_name = "StyleHub: pipeline BigQuery job failed"
  combiner     = "OR"

  conditions {
    display_name = "At least one failed job in 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.bigquery_job_errors.name}\" AND resource.type=\"bigquery_project\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "86400s"
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "A BigQuery job of the pipeline failed. Find it with: gcloud logging read 'resource.type=\"bigquery_project\" AND severity=ERROR' --freshness=1h. Fixes: docs/ERRORS.md."
    mime_type = "text/markdown"
  }
}
