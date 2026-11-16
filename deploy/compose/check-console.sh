#!/usr/bin/env bash
# Starts the core on the host and the review console container, then reviews a claim through the
# console in a real browser (Playwright). Needs claims analysed (check-agents.sh) and the console
# dependencies installed (npm ci). Used by CI.
set -euo pipefail

cd "$(dirname "$0")/../.."
jar=$(ls services/core/target/tramita-core-*.jar | grep -v original | head -1)
log="${RUNNER_TEMP:-/tmp}/core-console.log"
port="${CORE_PORT:-8080}"

java -jar "$jar" > "$log" 2>&1 &
core_pid=$!
trap 'kill $core_pid 2> /dev/null || true' EXIT
for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$port/actuator/health" > /dev/null; then break; fi
  sleep 2
done

docker compose -f deploy/compose/docker-compose.yml --env-file .env --profile console \
  up -d --build --wait console
cd web/console
npx playwright install --with-deps chromium > /dev/null
CONSOLE_URL="http://localhost:${CONSOLE_PORT:-4200}" npx playwright test
