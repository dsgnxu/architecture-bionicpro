# Airflow + OLAP (Задания 2–4)

Материалы ETL/OLAP для отчётов BionicPRO — в этой папке (не в корне репозитория).

```
airflow/
  dags/bionicpro_reports_etl.py   # DAG: telemetry → telemetry_daily (+ watermark)
  crm-db/init.sql                 # seed CRM + publication для Debezium
  telemetry-db/init.sql           # seed телеметрии
  clickhouse/init/01_schema.sql   # KafkaEngine, MV, report_mart_cdc
  Dockerfile / requirements.txt
  scripts/download-wheels.sh
  data/                           # runtime volumes (gitignore)
```

CDC (Debezium/Kafka): [`../cdc`](../cdc).  
API витрины: [`../reports-api`](../reports-api) → `report_mart_cdc`.

## DAG

- id: `bionicpro_reports_etl`
- schedule: `0 2 * * *`
- шаги: ensure schema → extract telemetry → load `telemetry_daily` (+ watermark)
- CRM dim приходит через CDC → `crm_clients`; MV собирает `report_mart_cdc`

ClickHouse: user `default` / password `clickhouse`.

## UI

http://localhost:8081 — admin / admin

```bash
docker compose exec airflow-scheduler airflow dags trigger bionicpro_reports_etl
```
