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

  # replace: a Windows checkout has CRLF line ends, which bash cannot run.
  metadata_startup_script = replace(templatefile("${path.module}/vm_startup.sh.tftpl", {
    project_id        = var.project_id
    secret_id         = google_secret_manager_secret.dotenv.secret_id
    github_repository = var.github_repository
  }), "\r", "")

  depends_on = [google_project_service.apis, google_secret_manager_secret_iam_member.pipeline_reads_dotenv]
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
