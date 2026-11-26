"""Minimal ClickHouse HTTP client (no clickhouse-connect dependency)."""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


def _base() -> str:
    return f"http://{settings.clickhouse_host}:{settings.clickhouse_port}/"


def _auth() -> tuple[str, str]:
    return (settings.clickhouse_user, settings.clickhouse_password)


def query_json(sql: str, timeout: float = 30.0) -> list[dict[str, Any]]:
    params = {"database": settings.clickhouse_database, "default_format": "JSON"}
    with httpx.Client(timeout=timeout, auth=_auth()) as client:
        resp = client.post(_base(), params=params, content=sql.encode("utf-8"))
        resp.raise_for_status()
        data = resp.json()
    return list(data.get("data") or [])


def ping() -> bool:
    with httpx.Client(timeout=5.0, auth=_auth()) as client:
        resp = client.get(f"{_base()}ping")
        return resp.status_code == 200
