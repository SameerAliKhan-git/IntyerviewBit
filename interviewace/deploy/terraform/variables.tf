variable "project_id" {
  description = "The GCP project ID to deploy resources to"
  type        = string
}

variable "region" {
  description = "The region to deploy Cloud Run in"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "interviewace"
}

variable "image" {
  description = "Container image to deploy. Build and push it before running apply."
  type        = string
  default     = null

  validation {
    condition     = var.image == null ? false : length(var.image) > 0
    error_message = "Set image, e.g. -var=\"image=gcr.io/PROJECT/interviewace:latest\"."
  }
}

variable "max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 5
}

variable "max_session_seconds" {
  description = "Hard cap on a single interview session, in seconds"
  type        = number
  default     = 1200
}

variable "max_concurrent_sessions" {
  description = "Maximum concurrent live sessions per instance"
  type        = number
  default     = 25
}

variable "billing_account_id" {
  description = "Billing account ID for the budget alert. Leave empty to skip the budget."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly budget threshold in USD for the alert"
  type        = number
  default     = 50
}
