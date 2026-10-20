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

# A new log metric takes a few minutes before an alert policy may use it;
# without this wait the first apply fails with "Cannot find metric(s)".
resource "time_sleep" "log_metric_ready" {
  create_duration = "180s"
  triggers        = { metric = google_logging_metric.bigquery_job_errors.id }
}

resource "google_monitoring_alert_policy" "bigquery_job_errors" {
  display_name = "StyleHub: pipeline BigQuery job failed"
  depends_on   = [time_sleep.log_metric_ready]
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

# The Cloud Run dashboard answers its health page; the check signs in with the
# Monitoring service agent (allowed in run.tf). 15 minutes from 3 regions stays
# inside the Cloud Run and uptime-check free tiers.
resource "google_monitoring_uptime_check_config" "dashboard" {
  display_name     = "StyleHub dashboard health"
  timeout          = "30s" # a cold start takes a few seconds
  period           = "900s"
  selected_regions = ["USA", "EUROPE", "ASIA_PACIFIC"]

  http_check {
    path         = "/_stcore/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    service_agent_authentication {
      type = "OIDC_TOKEN"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.dashboard.uri, "https://")
    }
  }
}

resource "google_monitoring_alert_policy" "dashboard_down" {
  display_name = "StyleHub: dashboard health check fails"
  combiner     = "OR"

  conditions {
    display_name = "Health check failed from every region for 30 minutes"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.dashboard.uptime_check_id}\" AND resource.type=\"uptime_url\""
      comparison      = "COMPARISON_GT"
      threshold_value = 2 # more than 2 of 3 regions see it down
      duration        = "1800s"
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
      }
    }
  }

  notification_channels = var.alert_notification_channels
}
