"""
ETL: CRM + telemetry (Postgres) → report_mart (ClickHouse) + etl_watermark.
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

CRM_DSN = "host=crm_db port=5432 dbname=crm user=crm password=crm"
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


def extract_crm(**_context) -> list[dict]:
    conn = psycopg2.connect(CRM_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, username, crm_status, prosthesis_model
                FROM clients
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "user_id": r[0],
            "username": r[1],
            "crm_status": r[2],
            "prosthesis_model": r[3],
        }
        for r in rows
    ]


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
    ti = context["ti"]
    crm_rows = ti.xcom_pull(task_ids="extract_crm") or []
    tel_rows = ti.xcom_pull(task_ids="extract_telemetry") or []

    crm_by_user = {c["username"]: c for c in crm_rows}

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

    mart_rows: list[dict] = []
    max_date: date | None = None
    for (_username, report_date_str), bucket in agg.items():
        crm = crm_by_user.get(bucket["username"], {})
        d = date.fromisoformat(report_date_str)
        if max_date is None or d > max_date:
            max_date = d
        mart_rows.append(
            {
                "user_id": crm.get("user_id") or bucket["user_id"],
                "username": bucket["username"],
                "report_date": report_date_str,
                "usage_hours": round(bucket["usage_hours"], 2),
                "movement_count": int(bucket["movement_count"]),
                "calibrations": int(bucket["calibrations"]),
                "crm_status": crm.get("crm_status", "unknown"),
                "prosthesis_model": crm.get("prosthesis_model", "unknown"),
            }
        )

    _ch_post("TRUNCATE TABLE IF EXISTS report_mart")
    if mart_rows:
        payload = ("\n".join(json.dumps(r, ensure_ascii=False) for r in mart_rows)).encode(
            "utf-8"
        )
        _ch_post("INSERT INTO report_mart FORMAT JSONEachRow", data=payload)

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
    description="ETL CRM + telemetry into ClickHouse report mart",
    schedule_interval="0 2 * * *",
    catchup=False,
    tags=["bionicpro", "reports", "etl"],
) as dag:
    t_schema = PythonOperator(
        task_id="ensure_olap_schema",
        python_callable=ensure_olap_schema,
    )
    t_crm = PythonOperator(
        task_id="extract_crm",
        python_callable=extract_crm,
    )
    t_tel = PythonOperator(
        task_id="extract_telemetry",
        python_callable=extract_telemetry,
    )
    t_load = PythonOperator(
        task_id="transform_and_load",
        python_callable=transform_and_load,
    )

    t_schema >> [t_crm, t_tel] >> t_load
