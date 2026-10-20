# Optional VM that runs Airflow with docker compose, so the 02:00 UTC schedule
# runs when the laptop is off. Off by default: about 25 USD a month when on.
# Turn on with enable_airflow_vm = true after the stylehub-dotenv secret has a value.
# Open the UI through IAP:
#   gcloud compute ssh stylehub-airflow --zone <zone> --tunnel-through-iap -- -L 8082:localhost:8082
resource "google_compute_instance" "airflow" {
  count        = var.enable_airflow_vm ? 1 : 0
  name         = "stylehub-airflow"
  machine_type = var.vm_machine_type
  zone         = var.vm_zone
  tags         = ["stylehub-airflow"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
    access_config {} # public IP for apt, GitHub and Docker Hub; no port is opened
  }

  service_account {
    email  = google_service_account.this["sa-pipeline"].email
    scopes = ["cloud-platform"] # rights come from IAM roles, not scopes
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  # Docker, secrets and the Airflow stack are set up by Ansible:
  #   infra/scripts/configure_vm.sh (playbook infra/ansible/airflow_vm.yml)

  depends_on = [google_project_service.apis, google_secret_manager_secret_iam_member.pipeline_reads_dotenv]
}

# Weekly snapshot of the boot disk, two kept: a broken VM is restored in minutes.
resource "google_compute_resource_policy" "weekly_snapshot" {
  count  = var.enable_airflow_vm ? 1 : 0
  name   = "stylehub-airflow-weekly"
  region = var.region

  snapshot_schedule_policy {
    schedule {
      weekly_schedule {
        day_of_weeks {
          day        = "SUNDAY"
          start_time = "04:00" # UTC, after the 02:00 run
        }
      }
    }
    retention_policy {
      max_retention_days    = 15
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "weekly_snapshot" {
  count = var.enable_airflow_vm ? 1 : 0
  name  = google_compute_resource_policy.weekly_snapshot[0].name
  disk  = google_compute_instance.airflow[0].name
  zone  = var.vm_zone
}

# SSH only from Google's IAP range; the Airflow port stays on localhost.
resource "google_compute_firewall" "iap_ssh" {
  count         = var.enable_airflow_vm ? 1 : 0
  name          = "stylehub-allow-iap-ssh"
  network       = "default"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["stylehub-airflow"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
