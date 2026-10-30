#!/usr/bin/env bash
# Exercises every service of the local stack with a real operation, not just its
# health check. Run with `make smoke` after `make up`.
set -euo pipefail

cd "$(dirname "$0")"
compose() { docker compose -f docker-compose.yml "$@"; }
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

POSTGRES_USER="${POSTGRES_USER:-tramita}"
POSTGRES_DB="${POSTGRES_DB:-tramita}"
OPENSEARCH="http://localhost:${OPENSEARCH_PORT:-9200}"
S3="http://localhost:${S3_API_PORT:-9000}"
S3_KEY="${S3_ACCESS_KEY:-tramita}"
S3_SECRET="${S3_SECRET_KEY:-change-me-local-only}"
RUN_ID="smoke$(date +%s)"

echo "PostgreSQL + pgvector"
nearest=$(compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -qtA -c "
  CREATE TEMP TABLE probe (label text, embedding vector(3));
  INSERT INTO probe VALUES ('near', '[1,1,1]'), ('far', '[9,9,9]');
  SELECT label FROM probe ORDER BY embedding <-> '[1.1,1,0.9]' LIMIT 1;")
[[ "$nearest" == "near" ]] && pass "vector similarity search" || fail "pgvector returned '$nearest'"

echo "Kafka"
kafka() { compose exec -T kafka "/opt/kafka/bin/$1" --bootstrap-server localhost:9092 "${@:2}"; }
kafka kafka-topics.sh --create --topic "$RUN_ID" --partitions 1 --replication-factor 1 > /dev/null
echo "hello-$RUN_ID" | kafka kafka-console-producer.sh --topic "$RUN_ID"
received=$(kafka kafka-console-consumer.sh --topic "$RUN_ID" --from-beginning --max-messages 1 --timeout-ms 30000 2> /dev/null)
[[ "$received" == "hello-$RUN_ID" ]] && pass "produce and consume" || fail "consumed '$received'"
kafka kafka-topics.sh --delete --topic "$RUN_ID"

echo "OpenSearch (Spanish analyzer)"
curl -fsS -X PUT "$OPENSEARCH/$RUN_ID" -H 'Content-Type: application/json' \
  -d '{"mappings":{"properties":{"text":{"type":"text","analyzer":"spanish"}}}}' > /dev/null
curl -fsS -X POST "$OPENSEARCH/$RUN_ID/_doc?refresh=true" -H 'Content-Type: application/json' \
  -d '{"text":"Rotura de la tubería de la cocina"}' > /dev/null
hits=$(curl -fsS "$OPENSEARCH/$RUN_ID/_search" -H 'Content-Type: application/json' \
  -d '{"query":{"match":{"text":"tuberías"}}}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["hits"]["total"]["value"])')
[[ "$hits" == "1" ]] && pass "stemmed full-text search" || fail "search returned $hits hits"
curl -fsS -X DELETE "$OPENSEARCH/$RUN_ID" > /dev/null

echo "Object store (S3 API)"
s3() { curl -fsS --aws-sigv4 "aws:amz:us-east-1:s3" --user "$S3_KEY:$S3_SECRET" "$@"; }
payload="$(mktemp)"
echo "documento-$RUN_ID" > "$payload"
s3 -X PUT "$S3/$RUN_ID" > /dev/null
s3 -T "$payload" "$S3/$RUN_ID/probe.txt" > /dev/null
downloaded=$(s3 "$S3/$RUN_ID/probe.txt")
[[ "$downloaded" == "documento-$RUN_ID" ]] && pass "put and get object" || fail "downloaded '$downloaded'"
s3 -X DELETE "$S3/$RUN_ID/probe.txt" > /dev/null
s3 -X DELETE "$S3/$RUN_ID" > /dev/null
rm -f "$payload"

echo "Temporal"
compose exec -T temporal temporal operator namespace describe --namespace default --address 127.0.0.1:7233 > /dev/null \
  && pass "default namespace is registered" || fail "default namespace missing"

echo "All services answered real requests."
