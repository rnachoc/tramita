#!/usr/bin/env bash
# Builds the images, loads them into a kind cluster, installs the chart and runs `helm test`
# (end to end in the cluster, and network policies). Expects kind, kubectl and helm, and a
# running kind cluster named by KIND_CLUSTER (default "tramita"). Used by CI.
set -euo pipefail

cd "$(dirname "$0")/../.."
cluster="${KIND_CLUSTER:-tramita}"
for image in core agents; do
  docker build -q -f "services/$image/Dockerfile" -t "tramita-$image:dev" . > /dev/null
done
docker build -q -f web/console/Dockerfile -t tramita-console:dev . > /dev/null
echo "  ok   images built"
kind load docker-image --name "$cluster" tramita-core:dev tramita-agents:dev tramita-console:dev > /dev/null
echo "  ok   images loaded into kind"

if ! helm install tramita deploy/helm/tramita --wait --wait-for-jobs --timeout 25m; then
  kubectl get pods -o wide
  kubectl get events --sort-by=.lastTimestamp | tail -30
  exit 1
fi
kubectl get pods
if ! helm test tramita --timeout 20m --logs; then
  kubectl get pods -o wide
  exit 1
fi
