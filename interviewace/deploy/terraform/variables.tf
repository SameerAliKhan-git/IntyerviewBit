variable "project_id" {
  description = "The GCP project ID to deploy resources to"
  type        = string
}

variable "region" {
  description = "The region to deploy Cloud Run in"
  type        = string
  default     = "us-central1"
}
