variable "project_id" {
  description = "GCP project id (GCP_PROJECT_ID in secrets/.env)."
  type        = string
}

variable "region" {
  description = "Where the bucket, the datasets and the image repository live (GCP_LOCATION)."
  type        = string
  default     = "asia-southeast1"
}

variable "bucket_location" {
  description = "Location of the Raw Zone bucket. Leave null to use var.region. A bucket cannot change location, so set this to what the existing bucket has (for example ASIA)."
  type        = string
  default     = null
}

variable "source_location" {
  description = "Location of the source dataset (the course tables). A dataset cannot change location, so set this to what it has now (for example US). Null uses var.region."
  type        = string
  default     = null
}

variable "bucket_name" {
  description = "GCS bucket of the Raw Zone, name only (GCS_BUCKET)."
  type        = string
}

variable "raw_prefix" {
  description = "Folder of the Raw Zone inside the bucket (RAW_PREFIX)."
  type        = string
  default     = "raw/stylehub"
}

variable "raw_retention_days" {
  description = "Raw daily batches are deleted after this many days. Same as setup_gcp.py."
  type        = number
  default     = 90
}

variable "noncurrent_retention_days" {
  description = "Old versions of a Raw file are deleted this many days after they were replaced."
  type        = number
  default     = 30
}

variable "datasets" {
  description = "BigQuery dataset ids, same names as BQ_SOURCE, BQ_BRONZE, BQ_STAGING, ..."
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
  description = "Tables and views in the staging dataset are deleted after this many days. It holds personal data. The live dataset already has 7."
  type        = number
  default     = 7
}

variable "github_repository" {
  description = "OWNER/REPO. Only this repository may sign in with Workload Identity Federation."
  type        = string
}

variable "artifact_repository" {
  description = "Name of the Docker image repository in Artifact Registry (AR_REPOSITORY)."
  type        = string
  default     = "stylehub"
}

variable "enable_ci" {
  description = "Create the service account and the dev datasets for .github/workflows/dbt-ci.yaml."
  type        = bool
  default     = true
}

variable "ci_dataset_prefix" {
  description = "dbt writes the CI copies to <prefix>_stylehub_silver, ... (DBT_DEV_USER=ci)."
  type        = string
  default     = "dbt_ci"
}
