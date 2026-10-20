variable "project_id" {
  description = "Google Cloud project id; dev shares the prod project."
  type        = string
}

variable "region" {
  description = "Region of the dev datasets."
  type        = string
  default     = "asia-southeast1"
}

variable "editors" {
  description = "Who may write dev data, e.g. [\"user:you@example.com\", \"serviceAccount:sa-pipeline@...\"]."
  type        = list(string)
  default     = []
}

variable "table_expiration_days" {
  description = "Staging tables delete themselves after this many days; CD rebuilds them on each deploy."
  type        = number
  default     = 1
}
