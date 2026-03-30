"""JWT-protected Synq API (shared OpenAI/ElevenLabs on server; per-user data via sub)."""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from synq.auth.credentials_store import UserSecrets, load_user_secrets, save_user_secrets
from synq.auth.jwt_tokens import create_access_token, decode_access_token, user_id_from_payload
from synq.auth.users import create_user, get_user, verify_login
from synq.integrations.google_context import google_user_context
from synq.orchestrator import Orchestrator
from synq.stt.base import TranscriptResult

load_dotenv()

router = APIRouter()
security = HTTPBearer(auto_error=False)

_orch: Optional[Orchestrator] = None


def _get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise HTTPException(
                status_code=503,
                detail="Server is missing OPENAI_API_KEY (set in environment for the API host).",
            )
        name = os.getenv("SYNQ_AGENT_NAME", "Synq")
        _orch = Orchestrator(agent_name=name, use_api=True, api_key=key, use_memory=True)
    return _orch


async def require_user_id(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> int:
    if creds is None or not (creds.scheme and creds.scheme.lower() == "bearer") or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    try:
        payload = decode_access_token(creds.credentials)
        return user_id_from_payload(payload)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None


class RegisterIn(BaseModel):
    name: str = Field(min_length=1)
    email: Optional[str] = None
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email_or_name: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class ChatOut(BaseModel):
    response: str


class TranscribeOut(BaseModel):
    text: str


class TtsIn(BaseModel):
    text: str = Field(min_length=1)


@router.post("/auth/register", response_model=TokenOut)
async def api_register(body: RegisterIn) -> TokenOut:
    uid = create_user(name=body.name, email=body.email, password=body.password)
    u = get_user(uid)
    token = create_access_token(user_id=uid, email=u.email if u else None)
    return TokenOut(access_token=token, user_id=uid)


@router.post("/auth/login", response_model=TokenOut)
async def api_login(body: LoginIn) -> TokenOut:
    uid = verify_login(email_or_name=body.email_or_name, password=body.password)
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    u = get_user(uid)
    token = create_access_token(user_id=uid, email=u.email if u else None)
    return TokenOut(access_token=token, user_id=uid)


@router.post("/v1/chat", response_model=ChatOut)
async def api_chat(body: ChatIn, user_id: int = Depends(require_user_id)) -> ChatOut:
    orch = _get_orchestrator()
    with google_user_context(user_id):
        reply = orch.process(
            TranscriptResult(text=body.message.strip(), confidence=1.0, is_final=True),
            user_id=user_id,
        )
    return ChatOut(response=reply)


@router.post("/v1/transcribe", response_model=TranscribeOut)
async def api_transcribe(
    user_id: int = Depends(require_user_id),
    audio: UploadFile = File(...),
    sample_rate: int = Form(16000),
) -> TranscribeOut:
    del sample_rate  # WAV embeds rate; kept for future raw-PCM uploads
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured on server")
    raw = await audio.read()
    if len(raw) < 500:
        raise HTTPException(status_code=400, detail="Audio too short")
    import io

    from openai import OpenAI

    model = os.getenv("SYNQ_SERVER_STT_MODEL", "whisper-1")
    buf = io.BytesIO(raw)
    buf.name = audio.filename or "audio.wav"
    client = OpenAI(api_key=key)
    tr = client.audio.transcriptions.create(model=model, file=buf)
    text = (getattr(tr, "text", None) or "").strip()
    return TranscribeOut(text=text)


@router.post("/v1/tts")
async def api_tts(body: TtsIn, _user_id: int = Depends(require_user_id)) -> Response:
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not configured on server")
    from elevenlabs.base_client import BaseElevenLabs

    voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "21m00Tcm4TlvDq8ikWAM"
    model = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
    client = BaseElevenLabs(api_key=key)
    chunks: list[bytes] = []
    stream = client.text_to_speech.convert(
        voice_id=voice,
        text=body.text,
        model_id=model,
        output_format="pcm_16000",
        optimize_streaming_latency=4,
    )
    for chunk in stream:
        if chunk:
            chunks.append(chunk)
    pcm = b"".join(chunks)
    return Response(
        content=pcm,
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": "16000", "X-PCM-Format": "s16le"},
    )


@router.post("/v1/me/google-token")
async def api_upload_google_token(
    user_id: int = Depends(require_user_id),
    token_file: UploadFile = File(...),
) -> dict:
    raw = (await token_file.read()).decode("utf-8", errors="replace")
    if len(raw) < 50:
        raise HTTPException(status_code=400, detail="Invalid token file")
    prev = load_user_secrets(user_id) or UserSecrets()
    prev.google_token_json = raw.strip()
    save_user_secrets(user_id, prev)
    return {"ok": True}
