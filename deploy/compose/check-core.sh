#!/usr/bin/env bash
# Starts the core service jar against the running Compose stack, seeds it with
# the generated policies and reads one back through the API. Needs `make up`,
# `make data-json` and a built jar (mvn -DskipTests package). Used by CI.
set -euo pipefail

cd "$(dirname "$0")/../.."
jar=$(ls services/core/target/tramita-core-*.jar | grep -v original | head -1)
log="${RUNNER_TEMP:-/tmp}/core.log"
port="${CORE_PORT:-8080}"
analyst_key=$(printf '%s' "$TRAMITA_API_KEYS" | tr ';' '\n' | awk -F: '$2 == "ANALYST" {print $3; exit}')

java -jar "$jar" > "$log" 2>&1 &
core_pid=$!
trap 'kill $core_pid 2> /dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$port/actuator/health" > /dev/null; then break; fi
  if ! kill -0 "$core_pid" 2> /dev/null; then tail -50 "$log"; echo "core exited during start-up" >&2; exit 1; fi
  sleep 2
done
curl -fsS "http://localhost:$port/actuator/health" | grep -q '"UP"' || { tail -50 "$log"; exit 1; }
echo "  ok   core started and migrated its schema"

TRAMITA_CORE_URL="http://localhost:$port" uv run tramita-seed
TRAMITA_CORE_URL="http://localhost:$port" uv run tramita-seed > /dev/null
echo "  ok   seeding is idempotent"

policy=$(python3 -c 'import json; print(json.load(open("data/generated/policies.json"))[0]["policy_number"])')
curl -fsS -H "X-Api-Key: $analyst_key" "http://localhost:$port/api/policies/$policy" | grep -q "\"policy_number\":\"$policy\"" \
  || { echo "policy $policy not readable through the API" >&2; exit 1; }
echo "  ok   policy $policy readable with the analyst role"

status=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port/api/policies/$policy")
[[ "$status" == "401" ]] || { echo "anonymous read returned $status, expected 401" >&2; exit 1; }
echo "  ok   anonymous requests are refused"
