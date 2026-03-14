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
    containers {
      image = "gcr.io/${var.project_id}/interviewace:latest"
      
      env {
        name  = "AGENT_MODEL"
        value = "gemini-2.5-flash-native-audio-preview"
      }
      
      env {
        name  = "USE_FIRESTORE"
        value = "true"
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
