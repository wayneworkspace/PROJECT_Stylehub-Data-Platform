# Streamlit dashboard on Cloud Run: HTTPS by Google, scales to zero, inside the
# free tier for a few visits a day. Nobody is allowed in without IAM
# (roles/run.invoker); open it with:
#   gcloud run services proxy stylehub-dashboard --region <region> --port 8501
# CD sets the tested image on each deploy, so Terraform ignores the image.
resource "google_cloud_run_v2_service" "dashboard" {
  name                = "stylehub-dashboard"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false # holds no data; the image is in Artifact Registry

  template {
    service_account = google_service_account.this["sa-dashboard"].email

    scaling {
      min_instance_count = 0 # no visitor, no cost
      max_instance_count = 1
    }

    containers {
      image = var.dashboard_placeholder_image

      ports {
        container_port = 8501
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true # CPU only while a request runs
      }

      dynamic "env" {
        for_each = {
          GCP_PROJECT_ID = var.project_id
          GCS_BUCKET     = var.bucket_name
          GCP_LOCATION   = var.region
          BQ_BRONZE      = var.datasets.bronze
          BQ_SILVER      = var.datasets.silver
          BQ_GOLD        = var.datasets.gold
          BQ_OPS         = var.datasets.ops
        }
        content {
          name  = env.key
          value = env.value
        }
      }

      startup_probe {
        http_get {
          path = "/_stcore/health"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_project_service.apis]
}

# Who may open the dashboard: the developers.
resource "google_cloud_run_v2_service_iam_member" "dashboard_viewers" {
  for_each = toset(var.developer_members)
  name     = google_cloud_run_v2_service.dashboard.name
  location = google_cloud_run_v2_service.dashboard.location
  role     = "roles/run.invoker"
  member   = each.value
}
