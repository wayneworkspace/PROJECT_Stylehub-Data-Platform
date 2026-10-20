variable "project_id" {
  description = "GCP project id (GCP_PROJECT_ID)."
  type        = string
}

variable "region" {
  description = "Region of the bucket, datasets and image repository (GCP_LOCATION)."
  type        = string
  default     = "asia-southeast1"
}

variable "bucket_location" {
  description = "Raw Zone bucket location; null uses region. Must match an existing bucket."
  type        = string
  default     = null
}

variable "source_location" {
  description = "Location of the course source dataset; null uses region."
  type        = string
  default     = null
}

variable "bucket_name" {
  description = "Raw Zone bucket name, without gs:// (GCS_BUCKET)."
  type        = string
}

variable "state_bucket" {
  description = "Bucket that holds the Terraform state; plan and apply need access."
  type        = string
}

variable "raw_prefix" {
  description = "Raw Zone folder inside the bucket (RAW_PREFIX)."
  type        = string
  default     = "raw/stylehub"
}

variable "raw_retention_days" {
  description = "Raw files are deleted after this many days; Bronze keeps the data."
  type        = number
  default     = 90
}

variable "noncurrent_retention_days" {
  description = "Old versions of a Raw file are deleted after this many days."
  type        = number
  default     = 30
}

variable "datasets" {
  description = "BigQuery dataset ids, same names as the BQ_* variables."
  type = object({
    source  = string
    bronze  = string
    staging = string
    silver  = string
    gold    = string
    ops     = string
  })
  default = {
    source  = "stylehub"
    bronze  = "stylehub_bronze"
    staging = "stylehub_staging"
    silver  = "stylehub_silver"
    gold    = "stylehub_gold"
    ops     = "stylehub_ops"
  }
}

variable "staging_table_expiration_days" {
  description = "Staging holds personal data, so its tables and views expire."
  type        = number
  default     = 7
}

variable "github_repository" {
  description = "OWNER/REPO allowed to sign in with Workload Identity Federation."
  type        = string
}

variable "artifact_repository" {
  description = "Artifact Registry repository for the images (AR_REPOSITORY)."
  type        = string
  default     = "stylehub"
}

variable "alert_notification_channels" {
  description = "Monitoring channel ids for the BigQuery job alert; empty shows incidents in the console only."
  type        = list(string)
  default     = []
}

variable "images_to_keep" {
  description = "Newest images kept per name in Artifact Registry; 0.5 GB of storage is free."
  type        = number
  default     = 2
}

variable "billing_account_id" {
  description = "Billing account for the budget alert, e.g. 012345-ABCDEF-678901; empty skips the budget (BILLING_ACCOUNT_ID)."
  type        = string
  default     = ""
}

variable "budget_usd" {
  description = "Monthly budget; e-mails go to billing admins at 50%, 90% and 100% of it."
  type        = number
  default     = 1
}

variable "developer_members" {
  description = "People who may act as sa-pipeline from a laptop instead of a key file, e.g. [\"user:you@example.com\"]."
  type        = list(string)
  default     = []
}

variable "dashboard_placeholder_image" {
  description = "Image the Cloud Run dashboard starts with; CD replaces it with the tested dashboard image."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
