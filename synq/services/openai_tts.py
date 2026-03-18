"""OpenAI TTS API - natural sounding voices."""

import tempfile
from pathlib import Path
from typing import Optional

from openai import OpenAI


class OpenAITTS:
    """OpenAI TTS API - production-quality voice."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "tts-1",
        voice: str = "alloy",
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)

    def speak_to_file(self, text: str) -> Path:
        """Generate speech, save to temp file, return path."""
        self._ensure_client()
        if not text.strip():
            raise ValueError("Empty text")
        r = self._client.audio.speech.create(model=self.model, voice=self.voice, input=text)
        path = Path(tempfile.mktemp(suffix=".mp3"))
        r.stream_to_file(str(path))
        return path
