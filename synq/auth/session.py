"""Active user for CLI voice agent + OS env injection for integrations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from synq.auth.credentials_store import UserSecrets, default_google_token_path, load_user_secrets
from synq.memory.db import get_db_path, init_db


def active_session_path() -> Path:
    return get_db_path().parent / "active_session.json"


def resolve_active_user_id() -> Optional[int]:
    """
    Priority: SYNQ_ACTIVE_USER_ID env -> active_session.json -> None (legacy .env only).
    """
    raw = os.getenv("SYNQ_ACTIVE_USER_ID", "").strip()
    if raw.isdigit():
        return int(raw)
    p = active_session_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            uid = data.get("user_id")
            if uid is not None and str(uid).isdigit():
                return int(uid)
        except Exception:
            pass
    return None


def write_active_session(user_id: int) -> None:
    p = active_session_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"user_id": user_id}, indent=2), encoding="utf-8")


def clear_active_session() -> None:
    p = active_session_path()
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


def apply_user_env(user_id: int) -> UserSecrets:
    """
    Merge per-user secrets into os.environ for STT/NLU/TTS/Google.
    Falls back to existing env/.env where a field is empty.
    """
    load_dotenv()
    init_db()
    merged = UserSecrets()
    stored = load_user_secrets(user_id)
    if stored:
        merged.openai_api_key = stored.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        merged.elevenlabs_api_key = stored.elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY", "")
        merged.elevenlabs_voice_id = stored.elevenlabs_voice_id or os.getenv("ELEVENLABS_VOICE_ID", "")
        merged.google_client_secrets_path = stored.google_client_secrets_path or os.getenv(
            "GOOGLE_CLIENT_SECRETS_PATH", ""
        )
        tok = stored.google_token_path.strip()
        if not tok:
            tok = default_google_token_path(user_id)
        merged.google_token_path = tok
    else:
        merged.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        merged.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "")
        merged.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
        merged.google_client_secrets_path = os.getenv("GOOGLE_CLIENT_SECRETS_PATH", "")
        merged.google_token_path = os.getenv("GOOGLE_TOKEN_PATH", "") or default_google_token_path(user_id)

    if merged.openai_api_key:
        os.environ["OPENAI_API_KEY"] = merged.openai_api_key
    if merged.elevenlabs_api_key:
        os.environ["ELEVENLABS_API_KEY"] = merged.elevenlabs_api_key
    if merged.elevenlabs_voice_id:
        os.environ["ELEVENLABS_VOICE_ID"] = merged.elevenlabs_voice_id
    if merged.google_client_secrets_path:
        os.environ["GOOGLE_CLIENT_SECRETS_PATH"] = merged.google_client_secrets_path
    if merged.google_token_path:
        os.environ["GOOGLE_TOKEN_PATH"] = merged.google_token_path
    return merged
