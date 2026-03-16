# Terraform provider configuration
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud Run Service Definition
# Satisfies the hackathon requirement of robust backend hosting
resource "google_cloud_run_v2_service" "interviewace" {
  name     = "interviewace-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "gcr.io/${var.project_id}/interviewace:latest"
      
      env {
        name  = "AGENT_MODEL"
        value = "gemini-live-2.5-flash-native-audio"
      }
      
      env {
        name  = "USE_FIRESTORE"
        value = "true"
      }

      env {
        name  = "USE_CLOUD_STORAGE"
        value = "true"
      }

      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.recordings.name
      }

      ports {
        container_port = 8080
      }
    }
  }
}

# Allow unauthenticated invocations for public hackathon demo
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = google_cloud_run_v2_service.interviewace.project
  location = google_cloud_run_v2_service.interviewace.location
  name     = google_cloud_run_v2_service.interviewace.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Firestore Database Instance for session grounding/storage
resource "google_firestore_database" "database" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

# Cloud Storage Bucket for session recordings
resource "google_storage_bucket" "recordings" {
  name     = "${var.project_id}-interviewace-recordings"
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90 # Auto-delete recordings after 90 days
    }
  }
}
