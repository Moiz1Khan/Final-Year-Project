"""
Synq web console: first-time setup, login, per-user API credentials.

Run: uvicorn synq.web.app:app --reload --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from synq.auth.credentials_store import (
    UserSecrets,
    default_google_token_path,
    load_user_secrets,
    save_user_secrets,
    user_data_dir,
)
from synq.auth.auth_token_file import auth_token_path, clear_auth_token, write_auth_token
from synq.auth.jwt_tokens import create_access_token
from synq.auth.session import active_session_path, clear_active_session, write_active_session
from synq.auth.users import (
    any_login_eligible_user,
    claim_default_user,
    create_user,
    get_user,
    update_user_display_name,
    user_count,
    verify_login,
)
from synq.api.router import router as synq_api_router
from synq.memory.db import init_db
from synq.web.auth_session import browser_login
from synq.web.google_oauth_config import google_oauth_enabled
from synq.web.google_routes import router as google_oauth_router

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Synq Console")
app.include_router(synq_api_router, prefix="/api")
app.include_router(google_oauth_router)
_session_secret = os.getenv("SYNQ_SESSION_SECRET", "").strip() or "dev-change-me-set-SYNQ_SESSION_SECRET"
app.add_middleware(SessionMiddleware, secret_key=_session_secret, same_site="lax")

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _auth_context() -> dict:
    return {"google_oauth_enabled": google_oauth_enabled()}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not any_login_eligible_user():
        return RedirectResponse("/setup", status_code=302)
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/app", status_code=302)


@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if any_login_eligible_user():
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@app.post("/setup", response_class=HTMLResponse)
async def setup_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    password2: str = Form(...),
    google_client_secrets_path: str = Form(""),
    google_token_path: str = Form(""),
    google_client_file: UploadFile | None = File(default=None),
):
    if any_login_eligible_user():
        return RedirectResponse("/login", status_code=302)
    if password != password2:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Passwords do not match."},
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Password must be at least 8 characters."},
            status_code=400,
        )
    try:
        uid = claim_default_user(name=name, email=email or None, password=password)
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": str(e)},
            status_code=400,
        )

    gpath = (google_client_secrets_path or "").strip()
    if google_client_file and google_client_file.filename:
        dest = user_data_dir(uid) / "google_client_secret.json"
        with dest.open("wb") as f:
            shutil.copyfileobj(google_client_file.file, f)
        gpath = str(dest.resolve())

    tok = (google_token_path or "").strip() or default_google_token_path(uid)
    prev = load_user_secrets(uid) or UserSecrets()
    secrets = UserSecrets(
        openai_api_key=prev.openai_api_key,
        elevenlabs_api_key=prev.elevenlabs_api_key,
        elevenlabs_voice_id=prev.elevenlabs_voice_id,
        google_client_secrets_path=gpath,
        google_token_path=tok,
        google_token_json=prev.google_token_json,
    )
    save_user_secrets(uid, secrets)

    browser_login(request, uid)
    return RedirectResponse("/app", status_code=302)


@app.get("/signup", response_class=HTMLResponse)
async def signup_get(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/app", status_code=302)
    if not any_login_eligible_user() and not google_oauth_enabled():
        return RedirectResponse("/setup", status_code=302)
    ctx = {"error": None, **_auth_context()}
    return templates.TemplateResponse(request, "signup.html", ctx)


@app.post("/signup", response_class=HTMLResponse)
async def signup_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    password2: str = Form(...),
):
    if not any_login_eligible_user() and not google_oauth_enabled():
        return RedirectResponse("/setup", status_code=302)
    if request.session.get("user_id"):
        return RedirectResponse("/app", status_code=302)
    if password != password2:
        ctx = {"error": "Passwords do not match.", **_auth_context()}
        return templates.TemplateResponse(request, "signup.html", ctx, status_code=400)
    if len(password) < 8:
        ctx = {"error": "Password must be at least 8 characters.", **_auth_context()}
        return templates.TemplateResponse(request, "signup.html", ctx, status_code=400)
    try:
        uid = create_user(name=name, email=email or None, password=password)
    except Exception as e:
        ctx = {"error": str(e), **_auth_context()}
        return templates.TemplateResponse(request, "signup.html", ctx, status_code=400)
    browser_login(request, uid)
    return RedirectResponse("/app", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if not any_login_eligible_user() and not google_oauth_enabled():
        return RedirectResponse("/setup", status_code=302)
    ctx = {"error": None, **_auth_context()}
    return templates.TemplateResponse(request, "login.html", ctx)


@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email_or_name: str = Form(...),
    password: str = Form(...),
):
    uid = verify_login(email_or_name=email_or_name, password=password)
    if uid is None:
        ctx = {
            "error": "Invalid email/username or password.",
            **_auth_context(),
        }
        return templates.TemplateResponse(request, "login.html", ctx, status_code=401)
    browser_login(request, uid)
    return RedirectResponse("/app", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    clear_active_session()
    clear_auth_token()
    return RedirectResponse("/login", status_code=302)


def _dashboard_context(user_id: int) -> dict:
    has_jwt = auth_token_path().exists()
    voice_synced = False
    try:
        p = active_session_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            voice_synced = int(data.get("user_id", 0)) == int(user_id)
    except Exception:
        pass
    existing = load_user_secrets(user_id)
    google_configured = bool(
        existing
        and (
            (existing.google_token_json or "").strip()
            or (existing.google_client_secrets_path or "").strip()
        )
    )
    return {
        "has_jwt": has_jwt,
        "voice_synced": voice_synced,
        "google_configured": google_configured,
    }


@app.get("/app", response_class=HTMLResponse)
async def app_home(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse("/login", status_code=302)
    u = get_user(uid)
    ctx = {"request": request, "user": u, "user_count": user_count()}
    ctx.update(_dashboard_context(int(uid)))
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/app/credentials", response_class=HTMLResponse)
async def credentials_get(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse("/login", status_code=302)
    existing = load_user_secrets(int(uid))
    u = get_user(int(uid))
    has_token = bool(existing and (existing.google_token_json or "").strip())
    ctx = {
        "openai": "" if not existing else "••••••••",
        "eleven": "" if not existing else "••••••••",
        "voice_id": existing.elevenlabs_voice_id if existing else "",
        "has_google_token_json": has_token,
        "user": u,
        **_auth_context(),
    }
    return templates.TemplateResponse(request, "credentials.html", ctx)


@app.post("/app/credentials", response_class=HTMLResponse)
async def credentials_post(
    request: Request,
    openai_api_key: str = Form(""),
    elevenlabs_api_key: str = Form(""),
    elevenlabs_voice_id: str = Form(""),
):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse("/login", status_code=302)

    prev = load_user_secrets(int(uid)) or UserSecrets()
    oa = openai_api_key.strip() or prev.openai_api_key
    el = elevenlabs_api_key.strip() or prev.elevenlabs_api_key
    v = elevenlabs_voice_id.strip() or prev.elevenlabs_voice_id

    save_user_secrets(
        int(uid),
        UserSecrets(
            openai_api_key=oa,
            elevenlabs_api_key=el,
            elevenlabs_voice_id=v,
            google_client_secrets_path=prev.google_client_secrets_path,
            google_token_path=prev.google_token_path or default_google_token_path(int(uid)),
            google_token_json=prev.google_token_json,
        ),
    )
    return RedirectResponse("/app/credentials?saved=1", status_code=302)


@app.post("/app/profile")
async def profile_post(request: Request, display_name: str = Form(...)):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse("/login", status_code=302)
    update_user_display_name(int(uid), display_name)
    return RedirectResponse("/app/credentials?saved=1", status_code=302)


@app.post("/app/active-voice-user")
async def set_active_voice_user(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse("/login", status_code=302)
    write_active_session(int(uid))
    u = get_user(int(uid))
    write_auth_token(create_access_token(user_id=int(uid), email=u.email if u else None))
    return RedirectResponse("/app?voice=1", status_code=302)
