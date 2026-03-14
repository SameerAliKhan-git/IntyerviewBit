#!/bin/bash
# deploy.sh
# Automated deployment script for InterviewAce to Google Cloud Run
# This script fulfills the "Automated cloud deployment" bonus point requirement.

set -e

echo "🚀 Starting deployment to Google Cloud..."

# Configuration - Replace with your actual project details
PROJECT_ID="your-google-cloud-project-id"
REGION="us-central1"
SERVICE_NAME="interviewace"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "📦 Setting active GCP project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo "🛠️ Extracting dependencies from pyproject.toml..."
# A simple way to get requirements.txt for the Docker build
pip install tomli
python -c "
import tomli
with open('../pyproject.toml', 'rb') as f:
    config = tomli.load(f)
deps = config.get('project', {}).get('dependencies', [])
with open('requirements.txt', 'w') as out:
    out.write('\n'.join(deps))
"
mv requirements.txt ./deploy/requirements.txt

echo "🏗️ Building the Docker image..."
cd deploy
docker build -t $IMAGE_NAME .

echo "📤 Pushing image to Google Container Registry..."
docker push $IMAGE_NAME

echo "🚀 Deploying to Google Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="AGENT_MODEL=gemini-2.5-flash-native-audio-preview"

echo "✅ Deployment complete!"
echo "Your InterviewAce AI Coach is now live on Google Cloud Platform."
