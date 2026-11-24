from __future__ import annotations

import json
import time
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.db import SessionLocal, UserProfile, init_db
from app import keycloak_client as kc
from app.session_store import SessionData, store

app = FastAPI(title="bionicpro-auth", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        # DB may start later; tables created on first consent write as fallback
        print(f"DB init deferred: {exc}")


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_seconds,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _roles_from_access_token(access_token: str) -> list[str]:
    payload = kc.decode_jwt_payload(access_token)
    realm_access = payload.get("realm_access") or {}
    return list(realm_access.get("roles") or [])


async def _ensure_fresh_access(session_id: str, data: SessionData) -> SessionData:
    if time.time() < data.access_expires_at:
        return data
    refresh = store.get_refresh_token(session_id)
    if not refresh:
        raise HTTPException(status_code=401, detail="Session expired")
    try:
        tokens = await kc.refresh_tokens(refresh)
    except httpx.HTTPError as exc:
        store.delete(session_id)
        raise HTTPException(status_code=401, detail="Refresh failed") from exc
    store.update_tokens(
        session_id,
        tokens["access_token"],
        tokens.get("refresh_token", refresh),
        int(tokens.get("expires_in", 120)),
    )
    updated = store.get(session_id)
    if not updated:
        raise HTTPException(status_code=401, detail="Session lost after refresh")
    return updated


async def require_session(request: Request, response: Response) -> tuple[str, SessionData]:
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid session")

    data = await _ensure_fresh_access(session_id, data)

    # Session rotation within valid access_token lifetime (anti fixation)
    new_id = store.rotate_session(session_id)
    if not new_id:
        raise HTTPException(status_code=401, detail="Session rotation failed")
    _set_session_cookie(response, new_id)
    response.headers["X-Session-Id"] = new_id
    rotated = store.get(new_id)
    if not rotated:
        raise HTTPException(status_code=401, detail="Session lost after rotation")
    return new_id, rotated


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/login")
async def login() -> RedirectResponse:
    verifier, challenge = kc.generate_pkce_pair()
    state = store.create_pkce_state(verifier)
    url = kc.build_authorization_url(state, challenge)
    return RedirectResponse(url=url, status_code=302)


@app.get("/auth/callback")
async def callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        raise HTTPException(status_code=400, detail=f"IdP error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    verifier = store.pop_pkce_verifier(state)
    if not verifier:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    try:
        tokens = await kc.exchange_code(code, verifier)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    access = tokens["access_token"]
    refresh = tokens["refresh_token"]
    expires_in = int(tokens.get("expires_in", 120))
    id_token = tokens.get("id_token")

    userinfo = {}
    try:
        userinfo = await kc.fetch_userinfo(access)
    except httpx.HTTPError:
        payload = kc.decode_jwt_payload(access)
        userinfo = {
            "sub": payload.get("sub"),
            "preferred_username": payload.get("preferred_username"),
            "email": payload.get("email"),
        }

    session_id = store.create_session(
        access,
        refresh,
        expires_in,
        id_token=id_token,
        user_sub=userinfo.get("sub"),
        username=userinfo.get("preferred_username") or userinfo.get("email"),
        email=userinfo.get("email"),
        roles=_roles_from_access_token(access),
    )

    payload = kc.decode_jwt_payload(access)
    idp = payload.get("identity_provider") or payload.get("idp")
    redirect_to = settings.frontend_url
    # Consent только при первом входе через Яндекс (если ещё не сохраняли в БД)
    if idp == "yandex":
        sub = userinfo.get("sub")
        if not _has_consent(sub):
            redirect_to = f"{settings.frontend_url}/?consent=1"

    resp = RedirectResponse(url=redirect_to, status_code=302)
    _set_session_cookie(resp, session_id)
    return resp


def _has_consent(subject: str | None) -> bool:
    if not subject:
        return False
    try:
        init_db()
        db = SessionLocal()
        try:
            row = db.query(UserProfile).filter_by(subject=subject).first()
            return bool(row and row.consent_given)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return False



@app.get("/auth/me")
async def me(session: tuple[str, SessionData] = Depends(require_session)):
    _, data = session
    return {
        "sub": data.user_sub,
        "username": data.username,
        "email": data.email,
        "roles": data.roles,
        "access_expires_at": data.access_expires_at,
    }


@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get(settings.session_cookie_name)
    id_token = None
    if session_id:
        data = store.get(session_id)
        if data:
            id_token = data.id_token
        store.delete(session_id)
    _clear_session_cookie(response)
    return {"logout_url": kc.build_logout_redirect(id_token)}


@app.get("/reports")
async def reports(session: tuple[str, SessionData] = Depends(require_session)):
    """Protected resource: only own prosthetic data conceptually (role-gated)."""
    _, data = session
    if "prothetic_user" not in data.roles and "administrator" not in data.roles:
        raise HTTPException(status_code=403, detail="Insufficient role for reports")
    return {
        "owner": data.username,
        "sub": data.user_sub,
        "report": {
            "prosthesis_usage_hours": 42.5,
            "calibrations": 3,
            "last_sync": "2026-03-22T12:00:00Z",
            "note": "Данные только по протезам текущего пользователя",
        },
    }


class ConsentBody(BaseModel):
    consent: bool = True


@app.post("/auth/consent")
async def consent(
    body: ConsentBody,
    session: tuple[str, SessionData] = Depends(require_session),
):
    """После аутентификации через Яндекс ID — согласие на использование профиля."""
    _, data = session
    if not body.consent:
        return JSONResponse({"status": "declined"}, status_code=200)

    profile_json: dict = {
        "sub": data.user_sub,
        "username": data.username,
        "email": data.email,
    }

    # Fetch Yandex profile if we have a Yandex access via Keycloak stored token path —
    # use userinfo already available; optionally call Yandex login info with broker token.
    try:
        userinfo = await kc.fetch_userinfo(data.access_token)
        profile_json.update(userinfo)
    except httpx.HTTPError:
        pass

    try:
        init_db()
        db = SessionLocal()
        try:
            row = db.query(UserProfile).filter_by(subject=data.user_sub).first()
            if not row:
                row = UserProfile(subject=data.user_sub or "unknown", provider="yandex")
                db.add(row)
            row.email = profile_json.get("email") or data.email
            row.first_name = profile_json.get("given_name") or profile_json.get("first_name")
            row.last_name = profile_json.get("family_name") or profile_json.get("last_name")
            row.display_name = (
                profile_json.get("name")
                or profile_json.get("display_name")
                or data.username
            )
            row.raw_profile = json.dumps(profile_json, ensure_ascii=False)
            row.consent_given = True
            # Detect provider from token
            payload = kc.decode_jwt_payload(data.access_token)
            if payload.get("identity_provider"):
                row.provider = str(payload["identity_provider"])
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to store profile: {exc}") from exc

    return {"status": "ok", "profile_saved": True}


@app.get("/auth/profile")
async def get_profile(session: tuple[str, SessionData] = Depends(require_session)):
    _, data = session
    db = SessionLocal()
    try:
        row = db.query(UserProfile).filter_by(subject=data.user_sub).first()
        if not row:
            return {"consent_given": False, "profile": None}
        return {
            "consent_given": row.consent_given,
            "profile": {
                "email": row.email,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "display_name": row.display_name,
                "provider": row.provider,
            },
        }
    finally:
        db.close()
