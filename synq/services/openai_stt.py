"""OpenAI Whisper API - production-grade STT."""

from pathlib import Path
from typing import Optional

from synq.stt.base import SpeechToText, TranscriptResult


class OpenAIWhisperSTT(SpeechToText):
    """OpenAI Whisper API - best accuracy, production-ready."""

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptResult:
        import tempfile
        import wave
        self._ensure_client()
        if len(audio_bytes) < 1000:
            return TranscriptResult(text="", confidence=0.0, is_final=True)

        path = Path(tempfile.mktemp(suffix=".wav"))
        try:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            with open(path, "rb") as af:
                r = self._client.audio.transcriptions.create(model=self.model, file=af)
            text = (r.text or "").strip()
            return TranscriptResult(text=text, confidence=1.0 if text else 0.0, is_final=True)
        finally:
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                pass

    def start_stream(self) -> None:
        pass

    def process_stream_chunk(self, chunk: bytes) -> Optional[TranscriptResult]:
        return None

    def stop_stream(self) -> Optional[TranscriptResult]:
        return None
