"""Encrypted per-user API keys and Google paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from synq.auth.crypto import decrypt_json, encrypt_json
from synq.memory.db import get_connection, get_db_path, init_db


@dataclass
class UserSecrets:
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    google_client_secrets_path: str = ""
    google_token_path: str = ""
    # Full authorized_user JSON (for API server; avoids shared disk paths per tenant)
    google_token_json: str = ""


def user_data_dir(user_id: int) -> Path:
    p = get_db_path().parent / "users" / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_google_token_path(user_id: int) -> str:
    return str(user_data_dir(user_id) / "google_token.json")


def save_user_secrets(user_id: int, secrets: UserSecrets) -> None:
    init_db()
    payload: Dict[str, Any] = {
        "openai_api_key": secrets.openai_api_key.strip(),
        "elevenlabs_api_key": secrets.elevenlabs_api_key.strip(),
        "elevenlabs_voice_id": secrets.elevenlabs_voice_id.strip(),
        "google_client_secrets_path": secrets.google_client_secrets_path.strip(),
        "google_token_path": secrets.google_token_path.strip(),
        "google_token_json": (secrets.google_token_json or "").strip(),
    }
    blob = encrypt_json(payload)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM user_credentials WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO user_credentials (user_id, payload_enc, updated_at)
            VALUES (?, ?, datetime('now'))
            """,
            (user_id, blob),
        )
        conn.commit()
    finally:
        conn.close()


def load_user_secrets(user_id: int) -> Optional[UserSecrets]:
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT payload_enc FROM user_credentials WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        data = decrypt_json(row["payload_enc"])
        return UserSecrets(
            openai_api_key=data.get("openai_api_key") or "",
            elevenlabs_api_key=data.get("elevenlabs_api_key") or "",
            elevenlabs_voice_id=data.get("elevenlabs_voice_id") or "",
            google_client_secrets_path=data.get("google_client_secrets_path") or "",
            google_token_path=data.get("google_token_path") or "",
            google_token_json=data.get("google_token_json") or "",
        )
    finally:
        conn.close()


def user_has_stored_credentials(user_id: int) -> bool:
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT 1 FROM user_credentials WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()
