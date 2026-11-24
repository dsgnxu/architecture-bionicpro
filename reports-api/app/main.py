from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import ch
from app import s3 as s3store
from app.config import settings

app = FastAPI(title="reports-api", version="1.2.0")

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
    try:
        return datetime.fromisoformat(str(raw).replace("Z", ""))
    except ValueError:
        return None


def _build_report_from_olap(
    username: Optional[str],
    user_id: Optional[str],
    date_from: Optional[date],
    effective_to: date,
    wm_date: date,
) -> dict[str, Any]:
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


@app.get("/health")
def health() -> dict:
    try:
        ok = ch.ping()
        wm = None
        try:
            wm = _watermark()
        except Exception:  # noqa: BLE001
            wm = None
        return {
            "status": "ok" if ok else "degraded",
            "clickhouse": "ok" if ok else "down",
            "watermark": wm.isoformat() if wm else None,
            "s3_bucket": settings.s3_bucket,
            "cdn": settings.cdn_public_url,
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
    Always return CDN URL (transparent for client).
    1) S3 pointer hit → no ClickHouse
    2) miss → OLAP → put S3 + pointer → CDN URL
    """
    if not username and not user_id:
        raise HTTPException(status_code=400, detail="username or user_id required")

    cache_username = username or user_id or "unknown"

    # Prefer S3 cache (works even if ClickHouse is stopped after first generate)
    cached = s3store.resolve_cached_report(cache_username)
    if cached:
        return {
            "owner": cache_username,
            "watermark": cached["watermark"],
            "s3_key": cached["s3_key"],
            "cdn_url": cached["cdn_url"],
            "cached": True,
            "source": "s3+cdn",
        }

    # Miss: need OLAP
    try:
        watermark = _watermark()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"No cached report in S3 and OLAP unavailable: {exc}",
        ) from exc

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
    report = _build_report_from_olap(
        username=username,
        user_id=user_id,
        date_from=date_from,
        effective_to=effective_to,
        wm_date=wm_date,
    )
    owner = str(report["owner"])
    s3_key = s3store.put_report_and_pointer(owner, wm_date.isoformat(), report)

    return {
        "owner": owner,
        "watermark": wm_date.isoformat(),
        "s3_key": s3_key,
        "cdn_url": s3store.cdn_url_for(s3_key),
        "cached": False,
        "source": "clickhouse→s3",
    }
