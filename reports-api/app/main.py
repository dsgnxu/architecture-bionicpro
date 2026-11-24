from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import ch
from app.config import settings

app = FastAPI(title="reports-api", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _watermark() -> Optional[datetime]:
    row = ch.query_json(
        f"""
        SELECT processed_to
        FROM etl_watermark
        WHERE pipeline = '{_escape(settings.etl_pipeline)}'
        ORDER BY processed_to DESC
        LIMIT 1
        """
    )
    if not row:
        return None
    raw = row[0].get("processed_to")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    # ClickHouse JSON: "YYYY-MM-DD HH:MM:SS"
    try:
        return datetime.fromisoformat(str(raw).replace("Z", ""))
    except ValueError:
        return None


@app.get("/health")
def health() -> dict:
    try:
        ok = ch.ping()
        wm = _watermark()
        return {
            "status": "ok" if ok else "degraded",
            "clickhouse": "ok" if ok else "down",
            "watermark": wm.isoformat() if wm else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "error": str(exc)}


@app.get("/reports")
def get_report(
    user_id: Optional[str] = Query(None, description="Internal CRM user_id"),
    username: Optional[str] = Query(None, description="Login username (preferred)"),
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
):
    """
    Read pre-aggregated report from OLAP mart.
    No heavy joins — data already prepared by Airflow ETL.
    """
    if not username and not user_id:
        raise HTTPException(status_code=400, detail="username or user_id required")

    watermark = _watermark()
    if watermark is None:
        raise HTTPException(
            status_code=409,
            detail="Report data is not ready yet — Airflow ETL has not run",
        )

    wm_date = watermark.date()

    if date_to and date_to > wm_date:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Requested period ends after ETL watermark ({wm_date.isoformat()}). "
                "Data for that period is not in OLAP yet."
            ),
        )
    if date_from and date_from > wm_date:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Requested from-date is after ETL watermark ({wm_date.isoformat()}). "
                "Data is not ready yet."
            ),
        )

    effective_to = min(date_to or wm_date, wm_date)
    where = ["1=1"]
    if username:
        where.append(f"username = '{_escape(username)}'")
    if user_id:
        where.append(f"user_id = '{_escape(user_id)}'")
    if date_from:
        where.append(f"report_date >= '{date_from.isoformat()}'")
    where.append(f"report_date <= '{effective_to.isoformat()}'")

    days = ch.query_json(
        f"""
        SELECT
            user_id,
            username,
            report_date,
            usage_hours,
            movement_count,
            calibrations,
            crm_status,
            prosthesis_model
        FROM report_mart
        WHERE {' AND '.join(where)}
        ORDER BY report_date
        """
    )

    if not days:
        raise HTTPException(
            status_code=404,
            detail="No report data in OLAP for this user (within processed period)",
        )

    for d in days:
        rd = d.get("report_date")
        if rd is not None and not isinstance(rd, str):
            d["report_date"] = str(rd)

    totals = {
        "usage_hours": round(sum(float(d["usage_hours"]) for d in days), 2),
        "movement_count": sum(int(d["movement_count"]) for d in days),
        "calibrations": sum(int(d["calibrations"]) for d in days),
    }

    first = days[0]
    return {
        "owner": first["username"],
        "user_id": first["user_id"],
        "crm_status": first["crm_status"],
        "prosthesis_model": first["prosthesis_model"],
        "period": {
            "from": days[0]["report_date"],
            "to": days[-1]["report_date"],
            "etl_watermark": wm_date.isoformat(),
        },
        "totals": totals,
        "days": days,
        "source": "clickhouse.report_mart",
    }
