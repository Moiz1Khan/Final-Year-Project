"""Persist JWT for local voice client (written on web login)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from synq.memory.db import get_db_path


def auth_token_path() -> Path:
    return get_db_path().parent / "auth_token.json"


def write_auth_token(access_token: str) -> None:
    p = auth_token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"access_token": access_token}, indent=2), encoding="utf-8")


def read_auth_token() -> Optional[str]:
    p = auth_token_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        t = (data.get("access_token") or "").strip()
        return t or None
    except Exception:
        return None


def clear_auth_token() -> None:
    p = auth_token_path()
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
