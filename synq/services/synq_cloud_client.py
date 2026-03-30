"""HTTP client for Synq shared API (JWT)."""

from __future__ import annotations

import io
import wave

import httpx


class SynqCloudClient:
    def __init__(self, *, base_url: str, access_token: str, timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._timeout = timeout_s

    def transcribe_pcm16_wav(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16)
        buf.seek(0)
        files = {"audio": ("audio.wav", buf.read(), "audio/wav")}
        data = {"sample_rate": str(sample_rate)}
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self.base_url}/api/v1/transcribe",
                headers=self._headers,
                files=files,
                data=data,
            )
        r.raise_for_status()
        js = r.json()
        return (js.get("text") or "").strip()

    def chat(self, message: str) -> str:
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self.base_url}/api/v1/chat",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"message": message},
            )
        r.raise_for_status()
        js = r.json()
        return (js.get("response") or "").strip()

    def tts_pcm16(self, text: str) -> tuple[bytes, int]:
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self.base_url}/api/v1/tts",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"text": text},
            )
        r.raise_for_status()
        sr = int(r.headers.get("X-Sample-Rate", "16000"))
        return r.content, sr

    def upload_google_token_json(self, json_text: str) -> None:
        files = {"token_file": ("google_token.json", json_text.encode("utf-8"), "application/json")}
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self.base_url}/api/v1/me/google-token",
                headers=self._headers,
                files=files,
            )
        r.raise_for_status()
