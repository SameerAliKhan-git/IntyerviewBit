terraform {
  required_version = ">= 1.5"
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

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
# Secret *values* are deliberately not managed here. Terraform state stores resource
# attributes in plaintext, so putting the API key in a .tf file or variable would move
# the leak from the repo into the state file. Create the versions out of band:
#   printf '%s' "$KEY" | gcloud secrets versions add interviewace-api-key --data-file=-

resource "google_secret_manager_secret" "api_key" {
  secret_id = "interviewace-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "session_secret" {
  secret_id = "interviewace-session-secret"
  replication {
    auto {}
  }
}

resource "google_service_account" "runtime" {
  account_id   = "interviewace-runtime"
  display_name = "InterviewAce Cloud Run runtime"
}

resource "google_secret_manager_secret_iam_member" "api_key_access" {
  secret_id = google_secret_manager_secret.api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "session_secret_access" {
  secret_id = google_secret_manager_secret.session_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# ---------------------------------------------------------------------------
# Cloud Run service
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "interviewace" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    # Session analytics live in the memory of the instance that owns the WebSocket, so
    # follow-up analytics reads must be routed back to that same instance.
    session_affinity = true

    # A mock interview is a single long-lived WebSocket; the 5-minute default would
    # terminate the call mid-answer.
    timeout = "3600s"

    containers {
      image = var.image

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "FALSE"
      }

      env {
        name  = "MAX_SESSION_SECONDS"
        value = tostring(var.max_session_seconds)
      }

      env {
        name  = "MAX_CONCURRENT_SESSIONS"
        value = tostring(var.max_concurrent_sessions)
      }

      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "SESSION_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.session_secret.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        failure_threshold     = 10
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.api_key_access,
    google_secret_manager_secret_iam_member.session_secret_access,
  ]
}

# Public access for the demo. Every anonymous session consumes the API key's quota, so
# keep the in-app rate limits in place. The budget alert below matters only if the key's
# project has billing enabled; on a free-tier key the failure mode is 429s, not a bill.
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = google_cloud_run_v2_service.interviewace.project
  location = google_cloud_run_v2_service.interviewace.location
  name     = google_cloud_run_v2_service.interviewace.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Cost guardrail
# ---------------------------------------------------------------------------

resource "google_billing_budget" "interviewace" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "InterviewAce monthly cap"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
}

output "service_url" {
  value       = google_cloud_run_v2_service.interviewace.uri
  description = "Public URL of the deployed InterviewAce service"
}
