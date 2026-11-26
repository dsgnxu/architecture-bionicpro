from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

import httpx

from app.config import settings


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return verifier, challenge


def _token_url() -> str:
    return (
        f"{settings.keycloak_internal_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/token"
    )


def _auth_url() -> str:
    return (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/auth"
    )


def _logout_url() -> str:
    return (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/logout"
    )


def build_authorization_url(state: str, code_challenge: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": settings.keycloak_client_id,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": settings.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{_auth_url()}?{urlencode(params)}"


async def exchange_code(code: str, code_verifier: str) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.keycloak_client_id,
        "client_secret": settings.keycloak_client_secret,
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_token_url(), data=data)
        resp.raise_for_status()
        return resp.json()


async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "client_id": settings.keycloak_client_id,
        "client_secret": settings.keycloak_client_secret,
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_token_url(), data=data)
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(access_token: str) -> dict[str, Any]:
    url = (
        f"{settings.keycloak_internal_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/userinfo"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        return resp.json()


def build_logout_redirect(id_token: str | None) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": settings.keycloak_client_id,
        "post_logout_redirect_uri": settings.frontend_url,
    }
    if id_token:
        params["id_token_hint"] = id_token
    return f"{_logout_url()}?{urlencode(params)}"


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload without verification (tokens already obtained from IdP)."""
    import json

    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode(payload + padding)
    return json.loads(raw)
