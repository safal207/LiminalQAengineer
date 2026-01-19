#!/bin/bash
set -euo pipefail

# 💖 LiminalQA Deployment Script
# One command to deploy everything!

echo "🚀 LiminalQA Deployment Starting..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}❌ $1 is not installed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ $1 found${NC}"
}

echo "🔍 Checking prerequisites..."
check_command docker
check_command kubectl
check_command helm

# Build Docker image
echo -e "${YELLOW}🏗️  Building Docker image...${NC}"
docker build -t liminalqa-ingest:latest -f liminalqa-ingest/Dockerfile .

# Tag for registry
echo -e "${YELLOW}🏷️  Tagging image...${NC}"
docker tag liminalqa-ingest:latest ghcr.io/safal207/liminalqaengineer/liminalqa-ingest:latest

# Push to registry
echo -e "${YELLOW}📤 Pushing to registry...${NC}"
docker push ghcr.io/safal207/liminalqaengineer/liminalqa-ingest:latest

# Deploy to Kubernetes
echo -e "${YELLOW}☸️  Deploying to Kubernetes...${NC}"
kubectl apply -f deploy/kubernetes/deployment.yaml

# Wait for rollout
echo -e "${YELLOW}⏳ Waiting for deployment...${NC}"
kubectl rollout status deployment/liminalqa-ingest -n liminalqa

# Get service URL
echo -e "${GREEN}✅ Deployment complete!${NC}"
kubectl get service liminalqa-ingest -n liminalqa

echo ""
echo -e "${GREEN}🎉 LiminalQA is live!${NC}"
echo ""
echo "📊 Monitor with: kubectl get pods -n liminalqa"
echo "📋 Logs with: kubectl logs -f deployment/liminalqa-ingest -n liminalqa"
echo "🔍 Port-forward: kubectl port-forward svc/liminalqa-ingest 8080:80 -n liminalqa"
echo ""
echo -e "${YELLOW}💖 Happy testing!${NC}"
