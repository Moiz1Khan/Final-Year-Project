"""Server-side Google OAuth (web) client for Sign in with Google + API scopes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, TypedDict


class GoogleOAuthConfig(TypedDict):
    client_secrets_path: str
    redirect_uri: str


def _resolve_secrets_path() -> Optional[str]:
    for key in (
        "SYNQ_GOOGLE_OAUTH_CLIENT_SECRETS_PATH",
        "GOOGLE_CLIENT_SECRETS_PATH",
    ):
        p = (os.getenv(key) or "").strip()
        if p and Path(p).is_file():
            return str(Path(p).resolve())
    return None


def _default_redirect_uri() -> str:
    return (
        (os.getenv("SYNQ_GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
        or "http://127.0.0.1:8765/auth/google/callback"
    )


def load_google_oauth_config() -> Optional[GoogleOAuthConfig]:
    """
    Path to OAuth client JSON (Web or Installed type) and redirect URI.
    In Google Cloud Console add the redirect URI (e.g. http://127.0.0.1:8765/auth/google/callback).
    """
    path = _resolve_secrets_path()
    if not path:
        return None
    return GoogleOAuthConfig(client_secrets_path=path, redirect_uri=_default_redirect_uri())


def client_config_has_web_or_installed(path: str) -> bool:
    try:
        data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return False
    return "web" in data or "installed" in data


def google_oauth_enabled() -> bool:
    cfg = load_google_oauth_config()
    return bool(cfg and client_config_has_web_or_installed(cfg["client_secrets_path"]))
