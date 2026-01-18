#!/bin/bash
set -euo pipefail

VERSION="${1:-2.1.0}"
NAMESPACE="network-ai"

echo "========================================"
echo "Network Consultant AI - Production Launch"
echo "Version: $VERSION"
echo "========================================"

echo "\n[1/6] Running production validation..."
python production_validation.py
if [ $? -ne 0 ]; then
    echo "❌ Validation failed. Aborting deployment."
    exit 1
fi

echo "\n[2/6] Running lock detection tests..."
python -m backend.tests.test_robust_lock_detection
if [ $? -ne 0 ]; then
    echo "❌ Lock tests failed. Aborting deployment."
    exit 1
fi

echo "\n[3/6] Building Docker image..."
docker build -t network-consultant:$VERSION -f Dockerfile.prod .

echo "\n[4/6] Deploying to Kubernetes..."
kubectl apply -f kubernetes/network-consultant-enterprise.yaml -n $NAMESPACE

echo "\n[5/6] Waiting for rollout..."
kubectl rollout status deployment/network-consultant-enterprise -n $NAMESPACE --timeout=5m

echo "\n[6/6] Running smoke tests..."
sleep 10
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app=network-consultant -o jsonpath="{.items[0].metadata.name}")
kubectl exec -n $NAMESPACE $POD_NAME -- curl -f http://localhost:8000/health || exit 1

echo "\n========================================"
echo "✅ Deployment successful!"
echo "Version: $VERSION"
echo "Namespace: $NAMESPACE"
echo "========================================"

echo "\nMonitoring commands:"
echo "  kubectl get pods -n $NAMESPACE"
echo "  kubectl logs -f deployment/network-consultant-enterprise -n $NAMESPACE"
echo "  kubectl port-forward -n $NAMESPACE svc/network-consultant 8000:8000"