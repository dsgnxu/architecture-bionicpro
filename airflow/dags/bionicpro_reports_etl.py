"""
ETL: telemetry (Postgres) → telemetry_daily (ClickHouse).
CRM dimensions arrive via Debezium CDC → Kafka → crm_clients.
MV report_mart_cdc_mv joins telemetry INSERT with crm_clients.

Schedule: daily at 02:00. Report API serves only periods <= watermark.
ClickHouse is accessed via HTTP API (stdlib urllib) — no extra pip packages.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from urllib import error, request
from urllib.parse import quote

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "airflow",
    "start_date": datetime(2025, 1, 1),
}

TEL_DSN = "host=telemetry_db port=5432 dbname=telemetry user=telemetry password=telemetry"
CH_URL = "http://clickhouse:8123/"
CH_USER = "default"
CH_PASSWORD = "clickhouse"
CH_DB = "bionicpro"
PIPELINE = "bionicpro_reports_etl"


def _ch_auth_header() -> dict[str, str]:
    import base64

    token = base64.b64encode(f"{CH_USER}:{CH_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _ch_post(sql: str, data: bytes | None = None, database: str | None = CH_DB) -> str:
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        **_ch_auth_header(),
    }
    if data is None:
        q = f"?database={database}" if database else ""
        req = request.Request(
            CH_URL + q,
            data=sql.encode("utf-8"),
            method="POST",
            headers=headers,
        )
    else:
        db = f"database={database}&" if database else ""
        headers = {
            "Content-Type": "application/json",
            **_ch_auth_header(),
        }
        req = request.Request(
            CH_URL + f"?{db}query={quote(sql)}",
            data=data,
            method="POST",
            headers=headers,
        )
    try:
        with request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ClickHouse error {exc.code}: {body}") from exc


def ensure_olap_schema(**_context) -> None:
    _ch_post("CREATE DATABASE IF NOT EXISTS bionicpro", database=None)
    # Legacy table (unused by API after Assignment 4)
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS report_mart
        (
            user_id String,
            username String,
            report_date Date,
            usage_hours Float64,
            movement_count UInt32,
            calibrations UInt32,
            crm_status String,
            prosthesis_model String
        )
        ENGINE = MergeTree
        ORDER BY (username, report_date)
        """
    )
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS etl_watermark
        (
            pipeline String,
            processed_to DateTime
        )
        ENGINE = ReplacingMergeTree
        ORDER BY pipeline
        """
    )
    # CDC dim + Kafka queue (may already exist from init SQL)
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS crm_clients_queue
        (
            user_id String,
            username String,
            full_name String,
            email Nullable(String),
            crm_status String,
            prosthesis_model String,
            registered_at Int32,
            `__deleted` String
        )
        ENGINE = Kafka
        SETTINGS
            kafka_broker_list = 'kafka:9092',
            kafka_topic_list = 'crm.public.clients',
            kafka_group_name = 'clickhouse_crm_clients',
            kafka_format = 'JSONEachRow',
            kafka_num_consumers = 1,
            kafka_skip_broken_messages = 100
        """
    )
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS crm_clients
        (
            user_id String,
            username String,
            full_name String,
            email String,
            crm_status String,
            prosthesis_model String,
            registered_at Date,
            updated_at DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY user_id
        """
    )
    _ch_post(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS crm_clients_mv
        TO crm_clients
        AS
        SELECT
            user_id,
            username,
            full_name,
            ifNull(email, '') AS email,
            crm_status,
            prosthesis_model,
            toDate(registered_at) AS registered_at,
            now() AS updated_at
        FROM crm_clients_queue
        WHERE `__deleted` != 'true'
        """
    )
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS telemetry_daily
        (
            user_id String,
            username String,
            report_date Date,
            usage_hours Float64,
            movement_count UInt32,
            calibrations UInt32
        )
        ENGINE = MergeTree
        ORDER BY (username, report_date)
        """
    )
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS report_mart_cdc
        (
            user_id String,
            username String,
            report_date Date,
            usage_hours Float64,
            movement_count UInt32,
            calibrations UInt32,
            crm_status String,
            prosthesis_model String
        )
        ENGINE = MergeTree
        ORDER BY (username, report_date)
        """
    )
    # Recreate MV so JOIN uses latest CRM row (ReplacingMergeTree may keep versions)
    _ch_post("DROP TABLE IF EXISTS report_mart_cdc_mv")
    _ch_post(
        """
        CREATE MATERIALIZED VIEW report_mart_cdc_mv
        TO report_mart_cdc
        AS
        SELECT
            t.user_id,
            t.username,
            t.report_date,
            t.usage_hours,
            t.movement_count,
            t.calibrations,
            ifNull(c.crm_status, 'unknown') AS crm_status,
            ifNull(c.prosthesis_model, 'unknown') AS prosthesis_model
        FROM telemetry_daily AS t
        LEFT JOIN
        (
            SELECT
                username,
                argMax(crm_status, updated_at) AS crm_status,
                argMax(prosthesis_model, updated_at) AS prosthesis_model
            FROM crm_clients
            GROUP BY username
        ) AS c ON t.username = c.username
        """
    )


def extract_telemetry(**_context) -> list[dict]:
    conn = psycopg2.connect(TEL_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, username, event_ts::date AS report_date,
                       usage_hours, movement_count, calibrations
                FROM telemetry_events
                WHERE event_ts::date < CURRENT_DATE
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "user_id": r[0],
            "username": r[1],
            "report_date": r[2].isoformat() if isinstance(r[2], date) else str(r[2]),
            "usage_hours": float(r[3]),
            "movement_count": int(r[4]),
            "calibrations": int(r[5]),
        }
        for r in rows
    ]


def transform_and_load(**context) -> None:
    """Load telemetry facts; MV joins CRM dim from CDC into report_mart_cdc."""
    ti = context["ti"]
    tel_rows = ti.xcom_pull(task_ids="extract_telemetry") or []

    agg: dict[tuple[str, str], dict] = {}
    for row in tel_rows:
        key = (row["username"], row["report_date"])
        bucket = agg.get(key)
        if not bucket:
            bucket = {
                "user_id": row["user_id"],
                "username": row["username"],
                "report_date": row["report_date"],
                "usage_hours": 0.0,
                "movement_count": 0,
                "calibrations": 0,
            }
            agg[key] = bucket
        bucket["usage_hours"] += row["usage_hours"]
        bucket["movement_count"] += row["movement_count"]
        bucket["calibrations"] += row["calibrations"]

    fact_rows: list[dict] = []
    max_date: date | None = None
    for (_username, report_date_str), bucket in agg.items():
        d = date.fromisoformat(report_date_str)
        if max_date is None or d > max_date:
            max_date = d
        fact_rows.append(
            {
                "user_id": bucket["user_id"],
                "username": bucket["username"],
                "report_date": report_date_str,
                "usage_hours": round(bucket["usage_hours"], 2),
                "movement_count": int(bucket["movement_count"]),
                "calibrations": int(bucket["calibrations"]),
            }
        )

    # Full reload of facts + mart (MV fills report_mart_cdc on INSERT)
    _ch_post("TRUNCATE TABLE IF EXISTS report_mart_cdc")
    _ch_post("TRUNCATE TABLE IF EXISTS telemetry_daily")

    if fact_rows:
        payload = ("\n".join(json.dumps(r, ensure_ascii=False) for r in fact_rows)).encode(
            "utf-8"
        )
        _ch_post("INSERT INTO telemetry_daily FORMAT JSONEachRow", data=payload)

    if max_date:
        processed_to = f"{max_date.isoformat()} 23:59:59"
    else:
        processed_to = f"{date.today().isoformat()} 00:00:00"

    wm_payload = json.dumps(
        {"pipeline": PIPELINE, "processed_to": processed_to},
        ensure_ascii=False,
    ).encode("utf-8")
    _ch_post("INSERT INTO etl_watermark FORMAT JSONEachRow", data=wm_payload)


with DAG(
    dag_id="bionicpro_reports_etl",
    default_args=default_args,
    description="ETL telemetry → CH; CRM via CDC; MV builds report_mart_cdc",
    schedule_interval="0 2 * * *",
    catchup=False,
    tags=["bionicpro", "reports", "etl", "cdc"],
) as dag:
    t_schema = PythonOperator(
        task_id="ensure_olap_schema",
        python_callable=ensure_olap_schema,
    )
    t_tel = PythonOperator(
        task_id="extract_telemetry",
        python_callable=extract_telemetry,
    )
    t_load = PythonOperator(
        task_id="transform_and_load",
        python_callable=transform_and_load,
    )

    t_schema >> t_tel >> t_load
