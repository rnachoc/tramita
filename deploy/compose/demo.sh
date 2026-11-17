#!/usr/bin/env bash
# The whole pipeline on a fresh clone, without credentials (ADR 0005): starts the stack,
# generates the synthetic dataset, indexes the policy conditions, starts the core, seeds it,
# ingests every claim, analyses them with the agents and scores the outcome. The core keeps
# running at the end so the claims can be reviewed in the console (`make console-up`).
# Needs Docker, uv, Java 17 with Maven and tesseract with Spanish data.
set -euo pipefail

cd "$(dirname "$0")/../.."
[[ -f .env ]] || { cp .env.example .env; echo "  ok   .env created from .env.example"; }
set -a && . ./.env && set +a
port="${CORE_PORT:-8080}"
log="${TMPDIR:-/tmp}/tramita-demo-core.log"

make up
make data
make index
(cd services/core && mvn -B -q -DskipTests package)
jar=$(ls services/core/target/tramita-core-*.jar | grep -v original | head -1)

java -jar "$jar" > "$log" 2>&1 &
core_pid=$!
trap 'kill $core_pid 2> /dev/null || true' EXIT
for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$port/actuator/health" > /dev/null; then break; fi
  if ! kill -0 "$core_pid" 2> /dev/null; then tail -50 "$log"; echo "core exited during start-up" >&2; exit 1; fi
  sleep 2
done
echo "  ok   core running on :$port (log: $log)"

export TRAMITA_CORE_URL="http://localhost:$port"
uv run tramita-seed
uv run tramita-ingest
uv run tramita-process
uv run tramita-eval-agents

echo
echo "Review the escalated claims: in another terminal run \`make console-up\` and open"
echo "http://localhost:4200. Press Ctrl+C here to stop the core."
wait "$core_pid"
