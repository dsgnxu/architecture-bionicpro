#!/usr/bin/env bash
# Создаёт LDAP User Federation + role mapper, если ещё нет.
set -euo pipefail

KC_URL="${KC_URL:-http://localhost:8180}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${REALM:-reports-realm}"
LDAP_NAME="${LDAP_NAME:-ldap-bionicpro-office}"

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

LDAP_ID=$(curl -sf -H "${AUTH}" \
  "${KC_URL}/admin/realms/${REALM}/components?type=org.keycloak.storage.UserStorageProvider" \
  | jq -r --arg n "${LDAP_NAME}" '.[] | select(.name==$n) | .id')

if [[ -z "${LDAP_ID}" || "${LDAP_ID}" == "null" ]]; then
  curl -sf -X POST -H "${AUTH}" -H "Content-Type: application/json" \
    "${KC_URL}/admin/realms/${REALM}/components" \
    -d "{
      \"name\": \"${LDAP_NAME}\",
      \"providerId\": \"ldap\",
      \"providerType\": \"org.keycloak.storage.UserStorageProvider\",
      \"config\": {
        \"enabled\": [\"true\"],
        \"priority\": [\"0\"],
        \"editMode\": [\"READ_ONLY\"],
        \"syncRegistrations\": [\"false\"],
        \"vendor\": [\"other\"],
        \"usernameLDAPAttribute\": [\"uid\"],
        \"rdnLDAPAttribute\": [\"uid\"],
        \"uuidLDAPAttribute\": [\"entryUUID\"],
        \"userObjectClasses\": [\"inetOrgPerson, organizationalPerson\"],
        \"connectionUrl\": [\"ldap://openldap:389\"],
        \"usersDn\": [\"ou=People,dc=bionicpro,dc=local\"],
        \"authType\": [\"simple\"],
        \"bindDn\": [\"cn=admin,dc=bionicpro,dc=local\"],
        \"bindCredential\": [\"admin\"],
        \"searchScope\": [\"1\"],
        \"useTruststoreSpi\": [\"ldapsOnly\"],
        \"connectionPooling\": [\"true\"],
        \"pagination\": [\"true\"],
        \"batchSizeForSync\": [\"1000\"],
        \"fullSyncPeriod\": [\"-1\"],
        \"changedSyncPeriod\": [\"-1\"],
        \"cachePolicy\": [\"DEFAULT\"]
      }
    }"
  echo "Created LDAP federation ${LDAP_NAME}"
  LDAP_ID=$(curl -sf -H "${AUTH}" \
    "${KC_URL}/admin/realms/${REALM}/components?type=org.keycloak.storage.UserStorageProvider" \
    | jq -r --arg n "${LDAP_NAME}" '.[] | select(.name==$n) | .id')
else
  echo "LDAP federation already exists: ${LDAP_ID}"
fi

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
        \"use.realm.roles.mapping\": [\"true\"]
      }
    }"
  echo "Created ldap-role-mapper"
else
  echo "ldap-role-mapper already exists"
fi

echo "LDAP federation configured."
