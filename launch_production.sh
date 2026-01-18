#!/bin/bash
set -e

VERSION="${1:-2.1.0}"
NAMESPACE="network-ai"

echo "🚀 Launching Network Consultant AI v$VERSION"

echo "📋 Step 1: Running validation tests..."
python production_validation.py
if [ $? -ne 0 ]; then
    echo "❌ Validation failed. Aborting deployment."
    exit 1
fi

echo "🧪 Step 2: Running lock detection tests..."
python -m backend.tests.test_robust_lock_detection
if [ $? -ne 0 ]; then
    echo "❌ Lock tests failed. Aborting deployment."
    exit 1
fi

echo "🏗️  Step 3: Building Docker image..."
docker build -t network-consultant:$VERSION .

echo "☸️  Step 4: Deploying to Kubernetes..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f kubernetes/network-consultant-enterprise.yaml -n $NAMESPACE

echo "⏳ Step 5: Waiting for rollout..."
kubectl rollout status deployment/network-consultant-enterprise -n $NAMESPACE --timeout=300s

echo "🔍 Step 6: Running smoke tests..."
POD=$(kubectl get pods -n $NAMESPACE -l app=network-consultant -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n $NAMESPACE $POD -- curl -sf http://localhost:8000/health || exit 1

echo "✅ Deployment complete!"
echo "📊 Monitor with: kubectl logs -f deployment/network-consultant-enterprise -n $NAMESPACE"
echo "🌐 Service URL: $(kubectl get svc -n $NAMESPACE network-consultant-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"