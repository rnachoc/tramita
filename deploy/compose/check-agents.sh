#!/usr/bin/env bash
# Starts the core against the running Compose stack, ingests every generated claim, analyses
# them with the agents (keyless unless ANTHROPIC_API_KEY is set) and gates the end-to-end
# outcome. Needs the core seeded (check-core.sh), the policy search indexed (make index) and a
# built jar. Used by CI.
set -euo pipefail

cd "$(dirname "$0")/../.."
jar=$(ls services/core/target/tramita-core-*.jar | grep -v original | head -1)
log="${RUNNER_TEMP:-/tmp}/core-agents.log"
port="${CORE_PORT:-8080}"

java -jar "$jar" > "$log" 2>&1 &
core_pid=$!
trap 'kill $core_pid 2> /dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$port/actuator/health" > /dev/null; then break; fi
  if ! kill -0 "$core_pid" 2> /dev/null; then tail -50 "$log"; echo "core exited during start-up" >&2; exit 1; fi
  sleep 2
done

export TRAMITA_CORE_URL="http://localhost:$port"
uv run tramita-ingest > /dev/null
echo "  ok   every claim ingested"
uv run tramita-process | tail -12
uv run tramita-eval-agents --gate
