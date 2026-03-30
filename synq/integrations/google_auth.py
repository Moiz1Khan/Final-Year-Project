"""
Google OAuth (Desktop/Installed App) helper.

Stores tokens locally in data/google_token.json by default.
When synq.integrations.google_context has an active user_id (API server), loads
that user's encrypted credentials (including optional inline google_token_json).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from synq.memory.db import get_db_path


def _default_token_path() -> Path:
    return get_db_path().parent / "google_token.json"


# One sign-in grants Calendar + Gmail (send + read). Use this so the same token works for all.
SYNQ_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def get_credentials(
    scopes: List[str],
    *,
    client_secrets_path: Optional[str] = None,
    token_path: Optional[str] = None,
):
    """
    Return google.oauth2.credentials.Credentials.

    If google_context has user_id (API request), use that user's stored Google config.
    Otherwise use env GOOGLE_CLIENT_SECRETS_PATH / GOOGLE_TOKEN_PATH.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    from synq.auth.credentials_store import default_google_token_path, load_user_secrets
    from synq.integrations.google_context import get_google_user_id

    request_scopes = list(SYNQ_OAUTH_SCOPES)
    uid = get_google_user_id()
    sec = load_user_secrets(uid) if uid is not None else None

    secrets = (
        (client_secrets_path or "").strip()
        or os.getenv("SYNQ_GOOGLE_OAUTH_CLIENT_SECRETS_PATH", "").strip()
        or os.getenv("GOOGLE_CLIENT_SECRETS_PATH", "").strip()
    )
    token_file: Optional[Path] = None

    if sec:
        secrets = (client_secrets_path or sec.google_client_secrets_path or secrets or "").strip()
        if sec.google_token_json.strip():
            try:
                info = json.loads(sec.google_token_json)
                creds = Credentials.from_authorized_user_info(info, scopes=request_scopes)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                if creds and creds.valid:
                    return creds
            except Exception:
                pass
        rel = (sec.google_token_path or "").strip()
        if rel:
            token_file = Path(rel)
        elif uid is not None:
            token_file = Path(default_google_token_path(uid))
    elif uid is not None:
        token_file = Path(default_google_token_path(uid))

    if not secrets:
        raise RuntimeError("Missing GOOGLE_CLIENT_SECRETS_PATH (OAuth client secrets JSON).")

    if token_file is None:
        token_file = Path(token_path or os.getenv("GOOGLE_TOKEN_PATH") or _default_token_path())
    token_file.parent.mkdir(parents=True, exist_ok=True)

    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), scopes=request_scopes)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if creds and creds.valid:
        return creds

    flow = InstalledAppFlow.from_client_secrets_file(secrets, scopes=request_scopes)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds
