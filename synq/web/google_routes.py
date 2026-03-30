"""Google OAuth: authorize + callback; stores refresh token in per-user UserSecrets."""

from __future__ import annotations

import logging
from typing import List

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from synq.auth.credentials_store import UserSecrets, default_google_token_path, load_user_secrets, save_user_secrets
from synq.auth.users import upsert_google_account
from synq.integrations.google_auth import SYNQ_OAUTH_SCOPES
from synq.web.auth_session import browser_login
from synq.web.google_oauth_config import load_google_oauth_config

log = logging.getLogger(__name__)

router = APIRouter(tags=["google-oauth"])


def _oauth_scopes() -> List[str]:
    return [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ] + list(SYNQ_OAUTH_SCOPES)


@router.get("/auth/google")
async def google_auth_start(request: Request):
    cfg = load_google_oauth_config()
    if not cfg:
        return RedirectResponse("/login?error=oauth_not_configured", status_code=302)
    import secrets as std_secrets

    state = std_secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    # Two-step OAuth uses a new Flow on callback; PKCE verifier would be lost.
    # Web client + client_secret does not require PKCE.
    flow = Flow.from_client_secrets_file(
        cfg["client_secrets_path"],
        scopes=_oauth_scopes(),
        redirect_uri=cfg["redirect_uri"],
        autogenerate_code_verifier=False,
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return RedirectResponse(authorization_url, status_code=302)


@router.get("/auth/google/callback")
async def google_auth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    if error:
        return RedirectResponse(f"/login?error=google_{error}", status_code=302)
    expected = request.session.get("google_oauth_state")
    request.session.pop("google_oauth_state", None)
    if not code or not state or state != expected:
        return RedirectResponse("/login?error=invalid_oauth_state", status_code=302)

    cfg = load_google_oauth_config()
    if not cfg:
        return RedirectResponse("/login?error=oauth_not_configured", status_code=302)

    try:
        flow = Flow.from_client_secrets_file(
            cfg["client_secrets_path"],
            scopes=_oauth_scopes(),
            redirect_uri=cfg["redirect_uri"],
            autogenerate_code_verifier=False,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception:
        log.exception("Google OAuth token exchange failed")
        return RedirectResponse("/login?error=token_exchange", status_code=302)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            r.raise_for_status()
            ui = r.json()
    except Exception:
        log.exception("Google userinfo failed")
        return RedirectResponse("/login?error=userinfo", status_code=302)

    google_sub = str(ui.get("id") or "").strip()
    if not google_sub:
        return RedirectResponse("/login?error=no_google_id", status_code=302)

    email = (ui.get("email") or "").strip() or None
    name = (ui.get("name") or "").strip() or (email.split("@")[0] if email else "User")

    try:
        uid = upsert_google_account(google_sub=google_sub, email=email, name=name)
    except Exception:
        log.exception("upsert_google_account failed")
        return RedirectResponse("/login?error=account", status_code=302)

    prev = load_user_secrets(uid) or UserSecrets()
    save_user_secrets(
        uid,
        UserSecrets(
            openai_api_key=prev.openai_api_key,
            elevenlabs_api_key=prev.elevenlabs_api_key,
            elevenlabs_voice_id=prev.elevenlabs_voice_id,
            google_client_secrets_path=prev.google_client_secrets_path,
            google_token_path=prev.google_token_path or default_google_token_path(uid),
            google_token_json=creds.to_json(),
        ),
    )

    browser_login(request, uid)
    return RedirectResponse("/app", status_code=302)
