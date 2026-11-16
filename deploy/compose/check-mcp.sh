#!/usr/bin/env bash
# Starts the core on the host and checks the MCP server against it (check-mcp.py). Needs the
# claims analysed (check-agents.sh) and the policy search indexed. Used by CI.
set -euo pipefail

cd "$(dirname "$0")/../.."
jar=$(ls services/core/target/tramita-core-*.jar | grep -v original | head -1)
port="${CORE_PORT:-8080}"
java -jar "$jar" > "${RUNNER_TEMP:-/tmp}/core-mcp.log" 2>&1 &
core_pid=$!
trap 'kill $core_pid 2> /dev/null || true' EXIT
for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$port/actuator/health" > /dev/null; then break; fi
  sleep 2
done
TRAMITA_CORE_URL="http://localhost:$port" uv run python deploy/compose/check-mcp.py
