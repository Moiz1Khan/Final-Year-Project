"""JWT access tokens for Synq API (per-user auth)."""

from __future__ import annotations

import os
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from synq.memory.db import get_db_path

ALGORITHM = "HS256"
DEFAULT_EXPIRE_DAYS = 7


def _secret() -> str:
    s = os.getenv("SYNQ_JWT_SECRET", "").strip()
    if s:
        return s
    path = get_db_path().parent / ".synq_jwt_secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    import secrets

    val = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(val, encoding="utf-8")
    warnings.warn(
        "SYNQ_JWT_SECRET not set; using data/.synq_jwt_secret (set SYNQ_JWT_SECRET in production).",
        stacklevel=2,
    )
    return val


def create_access_token(*, user_id: int, email: Optional[str] = None, expires_days: int = DEFAULT_EXPIRE_DAYS) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "uid": user_id,
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    if email:
        payload["email"] = email
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])


def user_id_from_payload(payload: dict[str, Any]) -> int:
    uid = payload.get("uid")
    if uid is not None and isinstance(uid, int):
        return uid
    sub = payload.get("sub")
    if sub is not None and str(sub).isdigit():
        return int(sub)
    raise ValueError("Invalid token payload: missing user id")
