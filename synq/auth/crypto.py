"""Symmetric encryption for per-user secrets at rest (Fernet)."""

from __future__ import annotations

import os
from pathlib import Path

from synq.memory.db import get_db_path


def _key_file() -> Path:
    return get_db_path().parent / ".synq_encryption_key"


def get_or_create_fernet_key() -> bytes:
    """
    Key from env SYNQ_ENCRYPTION_KEY (urlsafe base64, 32-byte raw when decoded),
    or persisted file data/.synq_encryption_key (generated once).
    """
    env = os.getenv("SYNQ_ENCRYPTION_KEY", "").strip()
    if env:
        # Fernet key is 32 url-safe base64-encoded bytes
        return env.encode("utf-8")

    path = _key_file()
    if path.exists():
        return path.read_bytes().strip()

    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return key


def encrypt_json(payload: dict) -> bytes:
    import json

    from cryptography.fernet import Fernet

    f = Fernet(get_or_create_fernet_key())
    return f.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def decrypt_json(blob: bytes) -> dict:
    import json

    from cryptography.fernet import Fernet

    f = Fernet(get_or_create_fernet_key())
    raw = f.decrypt(blob)
    return json.loads(raw.decode("utf-8"))
