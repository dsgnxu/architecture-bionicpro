"""Minimal S3-compatible client (LocalStack/MinIO) via HTTP + AWS SigV4 — no boto3."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.config import settings


def report_object_key(username: str, watermark_date: str) -> str:
    return f"users/{username}/wm={watermark_date}/report.json"


def latest_pointer_key(username: str) -> str:
    """Pointer object: always points at current report key for the user."""
    return f"users/{username}/latest.json"


def cdn_url_for(key: str) -> str:
    base = settings.cdn_public_url.rstrip("/")
    return f"{base}/{key.lstrip('/')}"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_headers(
    method: str,
    key: str,
    payload: bytes,
    content_type: str | None = None,
) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = settings.s3_region
    service = "s3"
    host = settings.s3_endpoint.split("://", 1)[-1].rstrip("/")
    canonical_uri = f"/{settings.s3_bucket}/{key}"
    payload_hash = hashlib.sha256(payload).hexdigest()

    headers_to_sign: dict[str, str] = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        headers_to_sign["content-type"] = content_type

    signed_header_keys = sorted(headers_to_sign.keys())
    canonical_headers = "".join(f"{k}:{headers_to_sign[k]}\n" for k in signed_header_keys)
    signed_headers = ";".join(signed_header_keys)
    canonical_request = "\n".join(
        [
            method,
            quote(canonical_uri, safe="/="),
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    k_date = _sign(("AWS4" + settings.s3_secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={settings.s3_access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    out = {
        "Authorization": authorization,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        out["Content-Type"] = content_type
    return out


def _object_url(key: str) -> str:
    return f"{settings.s3_endpoint.rstrip('/')}/{settings.s3_bucket}/{key}"


def object_exists(key: str) -> bool:
    headers = _sigv4_headers("HEAD", key, b"")
    with httpx.Client(timeout=15.0) as client:
        resp = client.head(_object_url(key), headers=headers)
    if resp.status_code in (403, 404):
        return False
    if resp.status_code >= 400:
        resp.raise_for_status()
    return True


def get_json(key: str) -> Optional[dict[str, Any]]:
    headers = _sigv4_headers("GET", key, b"")
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(_object_url(key), headers=headers)
    if resp.status_code in (403, 404):
        return None
    resp.raise_for_status()
    return resp.json()


def put_json(key: str, body: dict[str, Any]) -> None:
    payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
    headers = _sigv4_headers("PUT", key, payload, content_type="application/json")
    headers["Cache-Control"] = "public, max-age=600"
    with httpx.Client(timeout=30.0) as client:
        resp = client.put(_object_url(key), content=payload, headers=headers)
        resp.raise_for_status()


def resolve_cached_report(username: str) -> Optional[dict[str, str]]:
    """
    Return s3_key + watermark from pointer without ClickHouse.
    Enables serving CDN URL when OLAP is down after first generation.
    """
    pointer = get_json(latest_pointer_key(username))
    if not pointer:
        return None
    key = pointer.get("s3_key")
    if not key or not isinstance(key, str):
        return None
    if not object_exists(key):
        return None
    return {
        "s3_key": key,
        "watermark": str(pointer.get("watermark") or ""),
        "cdn_url": cdn_url_for(key),
    }


def put_report_and_pointer(username: str, watermark_date: str, body: dict[str, Any]) -> str:
    key = report_object_key(username, watermark_date)
    put_json(key, body)
    put_json(
        latest_pointer_key(username),
        {"s3_key": key, "watermark": watermark_date, "owner": username},
    )
    return key
