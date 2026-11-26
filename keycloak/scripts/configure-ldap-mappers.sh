#!/usr/bin/env bash
# После старта Keycloak добавляет role mapper LDAP groups → realm roles.
# Требует: curl, jq. Запускать, когда Keycloak уже импортировал realm.

set -euo pipefail

KC_URL="${KC_URL:-http://localhost:8180}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${REALM:-reports-realm}"
LDAP_NAME="${LDAP_NAME:-ldap-bionicpro-office}"

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

LDAP_ID=$(curl -sf -H "${AUTH}" \
  "${KC_URL}/admin/realms/${REALM}/components?type=org.keycloak.storage.UserStorageProvider" \
  | jq -r --arg n "${LDAP_NAME}" '.[] | select(.name==$n) | .id')

if [[ -z "${LDAP_ID}" || "${LDAP_ID}" == "null" ]]; then
  echo "LDAP provider '${LDAP_NAME}' not found. Check realm import."
  exit 1
fi

echo "LDAP component id: ${LDAP_ID}"

# group-ldap-mapper
EXISTING=$(curl -sf -H "${AUTH}" \
  "${KC_URL}/admin/realms/${REALM}/components?parent=${LDAP_ID}&type=org.keycloak.storage.ldap.mappers.LDAPStorageMapper" \
  | jq -r '.[] | select(.name=="ldap-group-mapper") | .id')

if [[ -z "${EXISTING}" || "${EXISTING}" == "null" ]]; then
  curl -sf -X POST -H "${AUTH}" -H "Content-Type: application/json" \
    "${KC_URL}/admin/realms/${REALM}/components" \
    -d "{
      \"name\": \"ldap-group-mapper\",
      \"providerId\": \"group-ldap-mapper\",
      \"providerType\": \"org.keycloak.storage.ldap.mappers.LDAPStorageMapper\",
      \"parentId\": \"${LDAP_ID}\",
      \"config\": {
        \"groups.dn\": [\"ou=Groups,dc=bionicpro,dc=local\"],
        \"group.name.ldap.attribute\": [\"cn\"],
        \"group.object.classes\": [\"groupOfNames\"],
        \"membership.ldap.attribute\": [\"member\"],
        \"membership.attribute.type\": [\"DN\"],
        \"membership.user.ldap.attribute\": [\"uid\"],
        \"mode\": [\"READ_ONLY\"],
        \"user.roles.retrieve.strategy\": [\"LOAD_GROUPS_BY_MEMBER_ATTRIBUTE\"],
        \"memberof.ldap.attribute\": [\"memberOf\"],
        \"drop.non.existing.groups.during.sync\": [\"false\"],
        \"groups.path\": [\"/\"]
      }
    }"
  echo "Created group-ldap-mapper"
else
  echo "group-ldap-mapper already exists"
fi

# role-ldap-mapper: map LDAP groups to realm roles with same names
EXISTING_ROLE=$(curl -sf -H "${AUTH}" \
  "${KC_URL}/admin/realms/${REALM}/components?parent=${LDAP_ID}&type=org.keycloak.storage.ldap.mappers.LDAPStorageMapper" \
  | jq -r '.[] | select(.name=="ldap-role-mapper") | .id')

if [[ -z "${EXISTING_ROLE}" || "${EXISTING_ROLE}" == "null" ]]; then
  curl -sf -X POST -H "${AUTH}" -H "Content-Type: application/json" \
    "${KC_URL}/admin/realms/${REALM}/components" \
    -d "{
      \"name\": \"ldap-role-mapper\",
      \"providerId\": \"role-ldap-mapper\",
      \"providerType\": \"org.keycloak.storage.ldap.mappers.LDAPStorageMapper\",
      \"parentId\": \"${LDAP_ID}\",
      \"config\": {
        \"roles.dn\": [\"ou=Groups,dc=bionicpro,dc=local\"],
        \"role.name.ldap.attribute\": [\"cn\"],
        \"role.object.classes\": [\"groupOfNames\"],
        \"membership.ldap.attribute\": [\"member\"],
        \"membership.attribute.type\": [\"DN\"],
        \"membership.user.ldap.attribute\": [\"uid\"],
        \"mode\": [\"READ_ONLY\"],
        \"user.roles.retrieve.strategy\": [\"LOAD_ROLES_BY_MEMBER_ATTRIBUTE\"],
        \"memberof.ldap.attribute\": [\"memberOf\"],
        \"use.realm.roles.mapping\": [\"true\"],
        \"use.client.roles.mapping\": [\"false\"]
      }
    }"
  echo "Created ldap-role-mapper (LDAP groups → realm roles)"
else
  echo "ldap-role-mapper already exists"
fi

echo "LDAP mappers configured."
