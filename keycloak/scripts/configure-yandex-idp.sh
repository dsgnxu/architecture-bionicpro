#!/usr/bin/env bash
# Создаёт IdP Яндекс через russian-providers (providerId=yandex), без OIDC/openid scope.
set -euo pipefail

KC_URL="${KC_URL:-http://localhost:8180}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${REALM:-reports-realm}"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

YANDEX_CLIENT_ID="${YANDEX_CLIENT_ID:-YANDEX_CLIENT_ID_PLACEHOLDER}"
YANDEX_CLIENT_SECRET="${YANDEX_CLIENT_SECRET:-YANDEX_CLIENT_SECRET_PLACEHOLDER}"

echo "Waiting for Keycloak..."
for i in $(seq 1 60); do
  if curl -sf "${KC_URL}/realms/${REALM}" >/dev/null; then
    break
  fi
  sleep 2
done

TOKEN=$(curl -sf \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASS}" \
  -d "grant_type=password" \
  "${KC_URL}/realms/master/protocol/openid-connect/token" | jq -r .access_token)
AUTH="Authorization: Bearer ${TOKEN}"

HAS_YANDEX=$(curl -sf -H "${AUTH}" "${KC_URL}/admin/serverinfo" \
  | jq -r '[.identityProviders[]? | select(.id=="yandex")] | length')
if [[ "${HAS_YANDEX}" == "0" ]]; then
  echo "ERROR: Social provider 'yandex' not loaded."
  echo "Run: ./keycloak/scripts/download-russian-providers.sh && docker compose up -d --force-recreate keycloak"
  exit 1
fi

BODY=$(cat <<EOF
{
  "alias": "yandex",
  "displayName": "Yandex ID",
  "providerId": "yandex",
  "enabled": true,
  "updateProfileFirstLoginMode": "on",
  "trustEmail": true,
  "storeToken": true,
  "addReadTokenRoleOnCreate": false,
  "authenticateByDefault": false,
  "linkOnly": false,
  "firstBrokerLoginFlowAlias": "first broker login",
  "config": {
    "clientId": "${YANDEX_CLIENT_ID}",
    "clientSecret": "${YANDEX_CLIENT_SECRET}",
    "defaultScope": "login:email login:info"
  }
}
EOF
)

CODE=$(curl -s -o /tmp/yandex-get.json -w '%{http_code}' -H "${AUTH}" \
  "${KC_URL}/admin/realms/${REALM}/identity-provider/instances/yandex" || true)

if [[ "${CODE}" == "200" ]]; then
  CUR=$(jq -r .providerId /tmp/yandex-get.json)
  if [[ "${CUR}" != "yandex" ]]; then
    echo "Removing legacy IdP providerId=${CUR} (OIDC sends openid → invalid_scope)"
    curl -sf -X DELETE -H "${AUTH}" \
      "${KC_URL}/admin/realms/${REALM}/identity-provider/instances/yandex"
    curl -sf -X POST -H "${AUTH}" -H "Content-Type: application/json" \
      "${KC_URL}/admin/realms/${REALM}/identity-provider/instances" \
      -d "${BODY}"
    echo "Created Yandex social IdP"
  else
    curl -sf -X PUT -H "${AUTH}" -H "Content-Type: application/json" \
      "${KC_URL}/admin/realms/${REALM}/identity-provider/instances/yandex" \
      -d "${BODY}"
    echo "Updated Yandex social IdP"
  fi
else
  curl -sf -X POST -H "${AUTH}" -H "Content-Type: application/json" \
    "${KC_URL}/admin/realms/${REALM}/identity-provider/instances" \
    -d "${BODY}"
  echo "Created Yandex social IdP"
fi

echo
echo "Проверьте на https://oauth.yandex.ru/ в приложении раздел «Доступы»:"
echo "  - Доступ к адресу электронной почты (login:email)"
echo "  - Доступ к логину, имени и фамилии, полу (login:info)"
echo "Callback URI:"
echo "  ${KC_URL}/realms/${REALM}/broker/yandex/endpoint"
