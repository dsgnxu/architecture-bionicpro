#!/usr/bin/env bash
# Скачивает JAR для Яндекс ID (Keycloak 21.1)
set -euo pipefail
DIR="$(cd "$(dirname "$0")/../providers" && pwd)"
mkdir -p "${DIR}"
cd "${DIR}"
BASE=https://repo1.maven.org/maven2
curl -fL -o keycloak-russian-providers-21.1.1.rsp.jar \
  "${BASE}/ru/playa/keycloak/keycloak-russian-providers/21.1.1.rsp/keycloak-russian-providers-21.1.1.rsp.jar"
curl -fL -o json-path-2.7.0.jar \
  "${BASE}/com/jayway/jsonpath/json-path/2.7.0/json-path-2.7.0.jar"
curl -fL -o json-smart-2.4.7.jar \
  "${BASE}/net/minidev/json-smart/2.4.7/json-smart-2.4.7.jar"
curl -fL -o accessors-smart-2.4.7.jar \
  "${BASE}/net/minidev/accessors-smart/2.4.7/accessors-smart-2.4.7.jar"
ls -la
echo "Restart Keycloak after download: docker compose up -d --force-recreate keycloak"
