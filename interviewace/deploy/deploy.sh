#!/usr/bin/env bash
#
# Deploys InterviewAce to Google Cloud Run via Cloud Build.
#
# This delegates to cloudbuild.yaml so there is exactly one build definition and one
# Dockerfile. Secrets are read from Secret Manager at runtime and are never passed on
# the command line, where they would land in shell history and build logs.
#
# Usage:
#   PROJECT_ID=my-project ./deploy.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-interviewace}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "ERROR: set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy.sh" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Project : ${PROJECT_ID}"
echo "Region  : ${REGION}"
echo "Service : ${SERVICE_NAME}"
echo

echo "==> Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project "${PROJECT_ID}"

echo "==> Checking required secrets"
missing=0
for secret in interviewace-api-key interviewace-session-secret; do
  if ! gcloud secrets describe "${secret}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  MISSING: ${secret}" >&2
    missing=1
  else
    echo "  ok: ${secret}"
  fi
done

if [[ "${missing}" -eq 1 ]]; then
  cat >&2 <<'EOF'

Create the missing secrets before deploying:

  printf '%s' "YOUR_GEMINI_API_KEY" | \
    gcloud secrets create interviewace-api-key --data-file=-

  python -c "import secrets;print(secrets.token_urlsafe(48))" | \
    gcloud secrets create interviewace-session-secret --data-file=-

EOF
  exit 1
fi

echo "==> Submitting build and deploy"
gcloud builds submit "${REPO_ROOT}" \
  --config "${REPO_ROOT}/cloudbuild.yaml" \
  --project "${PROJECT_ID}" \
  --substitutions "_REGION=${REGION},_SERVICE=${SERVICE_NAME}"

URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format 'value(status.url)')"

echo
echo "Deployment complete: ${URL}"
echo "Reminder: this service is public. Confirm a billing budget alert is configured."
