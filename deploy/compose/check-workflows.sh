#!/usr/bin/env bash
# Runs the core with claim events on, the workflow worker and the Kafka bridge against the
# running Compose stack, starts a workflow for a sample of claims and checks the whole loop with
# check-workflows.py. Needs the core seeded, the claims ingested (check-agents.sh) and the
# policy search indexed.
# Used by CI.
set -euo pipefail

cd "$(dirname "$0")/../.."
jar=$(ls services/core/target/tramita-core-*.jar | grep -v original | head -1)
logs="${RUNNER_TEMP:-/tmp}"
port="${CORE_PORT:-8080}"
export TRAMITA_CORE_URL="http://localhost:$port"
sample=$(python3 -c 'import json; print(",".join(c["claim_id"] for c in json.load(open("data/generated/claims.json"))[:20]))')

TRAMITA_EVENTS_ENABLED=true java -jar "$jar" > "$logs/core-events.log" 2>&1 &
pids=($!)
trap 'kill "${pids[@]}" 2> /dev/null || true' EXIT
for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$port/actuator/health" > /dev/null; then break; fi
  sleep 2
done

uv run tramita-worker > "$logs/worker.log" 2>&1 &
pids+=($!)
uv run tramita-bridge > "$logs/bridge.log" 2>&1 &
pids+=($!)

uv run tramita-start-claims --claims "$sample" --documents-wait 300 --review-wait 900
if ! uv run python deploy/compose/check-workflows.py "$sample"; then
  for log in core-events worker bridge; do echo "--- $log"; tail -30 "$logs/$log.log"; done
  exit 1
fi
