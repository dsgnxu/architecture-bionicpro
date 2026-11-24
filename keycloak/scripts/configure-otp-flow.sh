#!/usr/bin/env bash
# Делает OTP REQUIRED в browser flow (на случай, если import flow не применился).
set -euo pipefail

KC_URL="${KC_URL:-http://localhost:8180}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${REALM:-reports-realm}"

echo "Waiting for Keycloak..."
for i in $(seq 1 60); do
  if curl -sf "${KC_URL}/realms/master" >/dev/null; then
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

# Ensure CONFIGURE_TOTP is default required action
curl -sf -o /dev/null -X PUT -H "${AUTH}" -H "Content-Type: application/json" \
  "${KC_URL}/admin/realms/${REALM}/authentication/required-actions/CONFIGURE_TOTP" \
  -d '{
    "alias": "CONFIGURE_TOTP",
    "name": "Configure OTP",
    "providerId": "CONFIGURE_TOTP",
    "enabled": true,
    "defaultAction": true,
    "priority": 10,
    "config": {}
  }' || true

EXECUTIONS=$(curl -sf -H "${AUTH}" \
  "${KC_URL}/admin/realms/${REALM}/authentication/flows/browser/executions")

OTP_ID=$(echo "${EXECUTIONS}" | jq -r '
  .[] | select(.displayName=="OTP Form" or .providerId=="auth-otp-form") | .id' | head -1)

if [[ -z "${OTP_ID}" || "${OTP_ID}" == "null" ]]; then
  EXECUTIONS=$(curl -sf -H "${AUTH}" \
    "${KC_URL}/admin/realms/${REALM}/authentication/flows/forms/executions" || echo "[]")
  OTP_ID=$(echo "${EXECUTIONS}" | jq -r '
    .[] | select(.displayName=="OTP Form" or .providerId=="auth-otp-form") | .id' | head -1)
fi

if [[ -n "${OTP_ID}" && "${OTP_ID}" != "null" ]]; then
  curl -sf -o /dev/null -X PUT -H "${AUTH}" -H "Content-Type: application/json" \
    "${KC_URL}/admin/realms/${REALM}/authentication/flows/browser/executions" \
    -d "{\"id\": \"${OTP_ID}\", \"requirement\": \"REQUIRED\"}" || true
  echo "OTP Form set to REQUIRED (${OTP_ID})"
else
  echo "OTP Form execution not found — configure manually in Authentication → Browser/Forms"
fi

echo "OTP configuration done."
