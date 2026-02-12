#!/bin/bash

# ===========================================
# Build and Push Docker Images to Registry
# ===========================================

# Configuration
# Default to Docker Hub. Override as needed:
#   REGISTRY=docker.io REPO_OWNER=foreverlearning TAG=...
REGISTRY="${REGISTRY:-docker.io}"
REPO_OWNER="${REPO_OWNER:-fl-dev-ops}"
TAG="${TAG:-latest}"

echo "🔨 Building and pushing to: $REGISTRY/$REPO_OWNER"
echo ""

# Build and push backend
echo "📦 Building backend..."
docker build -t $REGISTRY/$REPO_OWNER/voicera-backend:$TAG ./voicera_backend
echo "🚀 Pushing backend..."
docker push $REGISTRY/$REPO_OWNER/voicera-backend:$TAG

# Build and push frontend
echo "📦 Building frontend..."
docker build -t $REGISTRY/$REPO_OWNER/voicera-frontend:$TAG ./voicera_frontend \
  --build-arg NEXT_PUBLIC_API_URL=https://api.voicera.foreverlearning.in \
  --build-arg NEXT_PUBLIC_JOHNAIC_SERVER_URL=https://voice.voicera.foreverlearning.in
echo "🚀 Pushing frontend..."
docker push $REGISTRY/$REPO_OWNER/voicera-frontend:$TAG

# Build and push voice server
echo "📦 Building voice server..."
docker build -t $REGISTRY/$REPO_OWNER/voicera-voice:$TAG ./voice_2_voice_server
echo "🚀 Pushing voice server..."
docker push $REGISTRY/$REPO_OWNER/voicera-voice:$TAG

# Build and push WhatsApp link sender
echo "📦 Building WhatsApp link sender..."
docker build -t $REGISTRY/$REPO_OWNER/voicera-whatsapp:$TAG ./apps/whatsapp-link-sender
echo "🚀 Pushing WhatsApp link sender..."
docker push $REGISTRY/$REPO_OWNER/voicera-whatsapp:$TAG

echo ""
echo "✅ All images pushed!"
echo ""
echo "Images:"
echo "  - $REGISTRY/$REPO_OWNER/voicera-backend:$TAG"
echo "  - $REGISTRY/$REPO_OWNER/voicera-frontend:$TAG"
echo "  - $REGISTRY/$REPO_OWNER/voicera-voice:$TAG"
echo "  - $REGISTRY/$REPO_OWNER/voicera-whatsapp:$TAG"
