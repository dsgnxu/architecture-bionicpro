#!/usr/bin/env bash
# Register Debezium Postgres connector (CRM clients → Kafka topic crm.public.clients).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CONNECT_URL="${CONNECT_URL:-http://localhost:8083}"
NAME="crm-postgres-connector"

echo "Waiting for Kafka Connect at ${CONNECT_URL} ..."
for i in $(seq 1 60); do
  if curl -sf "${CONNECT_URL}/" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    echo "Connect is not ready: ${CONNECT_URL}" >&2
    exit 1
  fi
  sleep 2
done

if curl -sf "${CONNECT_URL}/connectors/${NAME}" >/dev/null 2>&1; then
  echo "Connector ${NAME} already exists — deleting to re-register ..."
  curl -sf -X DELETE "${CONNECT_URL}/connectors/${NAME}" >/dev/null
  sleep 2
fi

echo "Registering ${NAME} ..."
curl -sf -X POST \
  -H "Content-Type: application/json" \
  --data @"${ROOT}/register-connector.json" \
  "${CONNECT_URL}/connectors" | python3 -m json.tool

echo
echo "Status:"
sleep 3
curl -sf "${CONNECT_URL}/connectors/${NAME}/status" | python3 -m json.tool
