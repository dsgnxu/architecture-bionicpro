# Airflow + OLAP (Задание 2)

Материалы ETL/OLAP для отчётов BionicPRO — в этой папке (не в корне репозитория).

```
airflow/
  dags/bionicpro_reports_etl.py   # DAG: CRM + telemetry → ClickHouse mart
  crm-db/init.sql                 # seed CRM (клиенты / модели протезов)
  telemetry-db/init.sql           # seed телеметрии (миосигналы / usage)
  clickhouse/init/01_schema.sql   # report_mart + etl_watermark
  Dockerfile / requirements.txt    # Airflow + psycopg2 (ClickHouse через HTTP)
  scripts/download-wheels.sh
  data/                           # runtime volumes (gitignore)
```

Отдельный API чтения витрины: [`../reports-api`](../reports-api) (FastAPI → ClickHouse).

## DAG

- id: `bionicpro_reports_etl`
- schedule: `0 2 * * *`
- шаги: ensure schema → extract CRM || extract telemetry → transform_and_load (+ watermark)

ClickHouse: user `default` / password `clickhouse` (через env в compose).

## UI

http://localhost:8081 — admin / admin

```bash
docker compose exec airflow-scheduler airflow dags trigger bionicpro_reports_etl
```
