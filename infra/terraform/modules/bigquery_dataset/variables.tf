variable "dataset_id" {
  description = "BigQuery dataset id."
  type        = string
}

variable "location" {
  description = "Dataset location; cannot change after creation."
  type        = string
}

variable "table_expiration_days" {
  description = "Default lifetime of new tables; null keeps them."
  type        = number
  default     = null
}

variable "members" {
  description = "Dataset IAM members: {key = {role, member}}; keys stay stable in state."
  type        = map(object({ role = string, member = string }))
  default     = {}
}
