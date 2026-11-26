"""In-memory session store: session_id -> tokens (access in memory, refresh encrypted)."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings
from app.crypto import decrypt_token, encrypt_token


@dataclass
class SessionData:
    access_token: str
    refresh_token_encrypted: str
    access_expires_at: float
    id_token: Optional[str] = None
    user_sub: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    roles: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    pkce_verifier: Optional[str] = None


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionData] = {}
        self._pkce: dict[str, str] = {}  # state -> code_verifier

    def create_pkce_state(self, code_verifier: str) -> str:
        state = secrets.token_urlsafe(32)
        with self._lock:
            self._pkce[state] = code_verifier
        return state

    def pop_pkce_verifier(self, state: str) -> Optional[str]:
        with self._lock:
            return self._pkce.pop(state, None)

    def create_session(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        *,
        id_token: Optional[str] = None,
        user_sub: Optional[str] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        roles: Optional[list[str]] = None,
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        data = SessionData(
            access_token=access_token,
            refresh_token_encrypted=encrypt_token(refresh_token),
            access_expires_at=time.time() + max(expires_in - 5, 1),
            id_token=id_token,
            user_sub=user_sub,
            username=username,
            email=email,
            roles=roles or [],
        )
        with self._lock:
            self._sessions[session_id] = data
        return session_id

    def get(self, session_id: str) -> Optional[SessionData]:
        with self._lock:
            data = self._sessions.get(session_id)
            if not data:
                return None
            if time.time() - data.created_at > settings.session_ttl_seconds:
                del self._sessions[session_id]
                return None
            return data

    def get_refresh_token(self, session_id: str) -> Optional[str]:
        data = self.get(session_id)
        if not data:
            return None
        return decrypt_token(data.refresh_token_encrypted)

    def update_tokens(
        self,
        session_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
    ) -> None:
        with self._lock:
            data = self._sessions.get(session_id)
            if not data:
                return
            data.access_token = access_token
            data.refresh_token_encrypted = encrypt_token(refresh_token)
            data.access_expires_at = time.time() + max(expires_in - 5, 1)

    def rotate_session(self, old_session_id: str) -> Optional[str]:
        """Rebind tokens to a new session id (anti session-fixation)."""
        with self._lock:
            data = self._sessions.pop(old_session_id, None)
            if not data:
                return None
            new_id = secrets.token_urlsafe(32)
            self._sessions[new_id] = data
            return new_id

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


store = SessionStore()
