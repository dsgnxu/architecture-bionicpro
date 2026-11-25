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
| bionicpro-auth | 8000 | BFF: PKCE, сессии, refresh, `/reports` gateway |
| keycloak | 8180 | IdP (OTP MFA, LDAP, Yandex broker); host 8180→container 8080 |
| openldap | 389 | Учётки представительства |
| auth_db | 5434 | Локальные профили после consent |
| keycloak_db | 5433 | БД Keycloak |
| crm_db / telemetry_db | 5435 / 5436 | Источники ETL / CDC (Задания 2–4) |
| clickhouse | 8123 | OLAP витрина отчётов (`report_mart_cdc`) |
| airflow-webserver | 8081 | Airflow DAG (telemetry → CH) |
| kafka / connect | 9092 / 8083 | CDC CRM: Kafka + Debezium |
| reports-api | 8001 | API отчётов из OLAP |

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
- Airflow UI: http://localhost:8081 (admin / admin)
- reports-api health: http://localhost:8001/health
- ClickHouse HTTP: http://localhost:8123/ping
- S3 (LocalStack): http://localhost:9002 (keys test/test)
- CDN (Nginx): http://localhost:8082/health
- Kafka Connect: http://localhost:8083/

---

## Задание 2 — Сервис отчётов (Airflow + ClickHouse)

Диаграмма ETL/OLAP: страница **Reports ETL OLAP** в [`docs/BionicPRO_C4_model.drawio.xml`](docs/BionicPRO_C4_model.drawio.xml).

Материалы задания 2 (seed, schema, DAG) — в [`airflow/`](airflow/) (см. [`airflow/README.md`](airflow/README.md)). API отчётов — [`reports-api/`](reports-api/).

### Компоненты

| Сервис | Порт | Назначение |
|--------|------|------------|
| crm_db | 5435 | Mock CRM + logical CDC (`airflow/crm-db`) |
| telemetry_db | 5436 | Mock телеметрия (`airflow/telemetry-db`) |
| clickhouse | 8123 | OLAP + `report_mart_cdc` (`airflow/clickhouse`) |
| kafka | 9092 | Apache Kafka (KRaft) |
| connect | 8083 | Debezium Postgres connector |
| airflow-webserver | 8081 | DAG `bionicpro_reports_etl` (telemetry only) |
| reports-api | 8001 | `GET /reports` (+ S3 cache / CDN URL) |
| bionicpro-auth | 8000 | Gateway `/reports` (self-only + session) |
| minio (LocalStack S3) | 9002 | S3-совместимое хранилище отчётов |
| cdn-nginx | 8082 | CDN reverse proxy + cache |

### ETL

DAG [`airflow/dags/bionicpro_reports_etl.py`](airflow/dags/bionicpro_reports_etl.py) (после Задания 4 — без mass SELECT из CRM):

1. Extract telemetry  
2. Агрегаты по username + день → `telemetry_daily`  
3. MV в ClickHouse JOIN с `crm_clients` (CDC) → `report_mart_cdc`  
4. Обновить `etl_watermark.processed_to`  

Расписание: `0 2 * * *` (ежедневно в 02:00). После старта вручную:

```bash
# при проблемах DNS в Docker:
./reports-api/scripts/download-wheels.sh
./airflow/scripts/download-wheels.sh

docker compose up --build -d
# UI http://localhost:8081 → DAGs → bionicpro_reports_etl → Trigger
docker compose exec airflow-scheduler airflow dags trigger bionicpro_reports_etl
```

### Проверка отчёта

1. Залогиньтесь как `prothetic1` / `prothetic123` (или LDAP `john.doe`).  
2. Дождитесь успешного DAG Run.  
3. UI → **Download Report** → данные из OLAP.  
4. Без логина `/reports` → 401.  
5. `?username=other` через BFF → 403.  
6. `?to=` дата после watermark → 409.

---

## Задание 3 — S3 + CDN (снижение нагрузки на OLAP)

Диаграмма: страница **Reports S3 CDN** в [`docs/BionicPRO_C4_model.drawio.xml`](docs/BionicPRO_C4_model.drawio.xml).  
CDN: [`cdn/nginx.conf`](cdn/nginx.conf).

### Поток

1. `GET /reports` (через BFF) → reports-api смотрит объект в MinIO.  
2. **Hit** → `{ cdn_url, cached: true }` без ClickHouse.  
3. **Miss** → SELECT витрины → PUT JSON в S3 → `{ cdn_url, cached: false }`.  
4. UI/клиент качает JSON по `cdn_url` (Nginx `proxy_cache`).

### Ключ объекта

```text
users/{username}/wm={YYYY-MM-DD}/report.json
```

Смена `etl_watermark` → новый ключ → естественная инвалидация CDN/S3-кэша.

### Проверка hit/miss (в т.ч. без OLAP)

UI только скачивает `.json` файл (не показывает содержимое на странице).

```bash
# 1) Первый запрос — generate → S3 (cached:false)
curl -s 'http://localhost:8001/reports?username=prothetic1' | python3 -m json.tool

# 2) Выключить ClickHouse — повтор всё равно отдаёт CDN URL из S3 pointer
docker compose stop clickhouse
curl -s 'http://localhost:8001/reports?username=prothetic1' | python3 -m json.tool
# ожидаем: "cached": true, "cdn_url": "http://localhost:8082/..."

# 3) Скачать файл напрямую с CDN (без UI)
curl -OJ "$(curl -s 'http://localhost:8001/reports?username=prothetic1' | python3 -c 'import sys,json; print(json.load(sys.stdin)["cdn_url"])')"

# 4) Вернуть OLAP
docker compose start clickhouse
```

---

## Задание 4 — CDC CRM (Debezium → Kafka → ClickHouse)

Диаграмма: страница **CRM CDC Kafka** (+ синие блоки на Page-1) в [`docs/BionicPRO_C4_model.drawio.xml`](docs/BionicPRO_C4_model.drawio.xml).  
Конфиг коннектора: [`cdc/`](cdc/).

### Поток

1. `crm_db` с `wal_level=logical` + publication `dbz_crm_publication` на `clients`.  
2. Debezium Connect читает WAL → Kafka topic `crm.public.clients`.  
3. ClickHouse `KafkaEngine` (`crm_clients_queue`) → MV → `crm_clients`.  
4. Airflow грузит только telemetry → `telemetry_daily`; MV → `report_mart_cdc`.  
5. `reports-api` читает `report_mart_cdc` (без SELECT из CRM OLTP).

### Подъём и регистрация коннектора

```bash
# Если crm_db уже был без logical decoding — recreate + bootstrap publication:
docker compose up -d --force-recreate crm_db kafka connect clickhouse
docker compose exec -T crm_db psql -U crm -d crm < cdc/bootstrap-crm-replication.sql

docker compose up -d
./cdc/register.sh
# ожидаем connector.state RUNNING
```

### Проверка CDC

```bash
# 1) Изменить CRM (OLTP) — без выгрузки в ETL
docker compose exec -T crm_db psql -U crm -d crm \
  -c "UPDATE clients SET crm_status='vip' WHERE username='prothetic1';"

# 2) Дождаться появления в ClickHouse dim
docker compose exec clickhouse clickhouse-client --password clickhouse \
  --query "SELECT user_id, username, crm_status FROM bionicpro.crm_clients FINAL ORDER BY username"

# 3) Пересобрать витрину (telemetry + MV join)
docker compose exec airflow-scheduler airflow dags trigger bionicpro_reports_etl

# 4) API читает новую витрину
curl -s 'http://localhost:8001/reports?username=prothetic1' | python3 -m json.tool
```

