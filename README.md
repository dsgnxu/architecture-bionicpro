# BionicPRO — Architecture Sprint (SSO / Security)

Задание 1: повышение безопасности системы.

## Архитектура (Задача 1)

- Диаграмма C4 (draw.io): [`docs/c4-identity.drawio`](docs/c4-identity.drawio)
- Описание: [`docs/architecture-identity.md`](docs/architecture-identity.md)

Ключевые решения:
- Keycloak — единый SSO; учётки представительства — из локального OpenLDAP.
- ПДн хранятся локально в регионе (`auth_db`).
- Access/refresh токены IdP **не** попадают на фронтенд — только HttpOnly session cookie от `bionicpro-auth` (BFF + PKCE).
- Внешние IdP (Яндекс ID и др.) — через Identity Brokering.

## Сервисы

| Сервис | Порт | Назначение |
|--------|------|------------|
| frontend | 3000 | React UI (без keycloak-js) |
| bionicpro-auth | 8000 | BFF: PKCE, сессии, refresh, ротация session id |
| keycloak | 8180 | IdP (OTP MFA, LDAP, Yandex broker); host 8180→container 8080 |
| openldap | 389 | Учётки представительства |
| auth_db | 5434 | Локальные профили после consent |
| keycloak_db | 5433 | БД Keycloak |

## Быстрый старт

```bash
docker compose up --build -d
# после готовности Keycloak (порт 8180):
chmod +x keycloak/scripts/*.sh
./keycloak/scripts/configure-ldap-federation.sh
./keycloak/scripts/configure-otp-flow.sh
./keycloak/scripts/configure-yandex-idp.sh
```

> Host-порт Keycloak: **8180** (8080 часто занят другими контейнерами).  
> Сборка `bionicpro-auth`: при проблемах DNS к PyPI сначала `./bionicpro-auth/scripts/download-wheels.sh`.

Откройте http://localhost:3000 → Login.

### Локальные пользователи Keycloak

При первом входе потребуется настроить OTP (Google Authenticator / FreeOTP).

| Username | Password | Role |
|----------|----------|------|
| user1 / user2 | password123 | user |
| admin1 | admin123 | administrator |
| prothetic1–3 | prothetic123 | prothetic_user |

### LDAP пользователи

База: `dc=bionicpro,dc=local` (`LDAP_DOMAIN=bionicpro.local`).

| uid | password | LDAP group → realm role |
|-----|----------|-------------------------|
| john.doe | password | prothetic_user |
| jane.smith | password | user |
| alex.johnson | password | prothetic_user |

После смены домена пересоздайте OpenLDAP и заново настройте federation:

```bash
docker compose up -d --force-recreate openldap
./keycloak/scripts/configure-ldap-federation.sh
```

## Задачи спринта

### Задача 2 — PKCE
Клиент `reports-frontend`: `pkce.code.challenge.method=S256`, confidential, без Direct Access Grants / Implicit. Code exchange только в `bionicpro-auth`.

### Задача 3 — bionicpro-auth
- Access token TTL ≤ 2 мин (`accessTokenLifespan: 120`)
- Refresh token на сервере (Fernet-шифрование)
- Access token в memory store
- Cookie `bionicpro_session`: HttpOnly (+ Secure при `COOKIE_SECURE=true`)
- Session TTL 30 мин > access TTL
- Авто-refresh + **ротация session id** на каждом защищённом запросе

### Задача 4 — LDAP
OpenLDAP в compose + User Federation: `./keycloak/scripts/configure-ldap-federation.sh`  
(LDAP groups `user` / `prothetic_user` → realm roles).

### Задача 5 — MFA
`CONFIGURE_TOTP` — default required action; OTP Form REQUIRED в browser flow  
(`./keycloak/scripts/configure-otp-flow.sh`). Первый вход — настройка Google Authenticator / FreeOTP.

### Задача 6 — Яндекс ID

Яндекс — это OAuth2, не OIDC. Обычный Keycloak **OIDC IdP** шлёт `scope=openid` → ошибка `invalid_scope`.  
Поэтому используется JAR `keycloak-russian-providers` (провайдер `yandex`):

```bash
./keycloak/scripts/download-russian-providers.sh
docker compose up -d --force-recreate keycloak
# в .env: YANDEX_CLIENT_ID / YANDEX_CLIENT_SECRET
./keycloak/scripts/configure-yandex-idp.sh
```

Приложение на https://oauth.yandex.ru/ :

- Callback: `http://localhost:8180/realms/reports-realm/broker/yandex/endpoint`
- **Доступы** (обязательно отметьте):
  - доступ к email (`login:email`)
  - доступ к логину, имени и фамилии (`login:info`)

После входа через Яндекс UI запросит consent; профиль сохраняется в `auth_db.user_profiles`.

## Артефакты сдачи (Задание 1)

| Требование | Файл / место |
|------------|----------------|
| Диаграмма draw.io | [`docs/BionicPRO_C4_model.drawio.xml`](docs/BionicPRO_C4_model.drawio.xml), [`docs/c4-identity.drawio`](docs/c4-identity.drawio) |
| PKCE | `bionicpro-auth` + `pkce.code.challenge.method=S256` в realm |
| Backend сессий | [`bionicpro-auth/`](bionicpro-auth/) |
| Frontend без Keycloak-js | [`frontend/src/`](frontend/src/) — cookie / `credentials: 'include'` |
| Экспорт realm | [`keycloak/keycloak-results-export.json`](keycloak/keycloak-results-export.json) |
| Яндекс ID | IdP `yandex` (russian-providers) + consent в FE/BFF |

## Полезные URL

- Keycloak Admin: http://localhost:8180 (admin / admin)
- Auth health: http://localhost:8000/health
- Login: http://localhost:8000/auth/login

