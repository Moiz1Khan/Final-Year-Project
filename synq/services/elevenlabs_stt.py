"""ElevenLabs Speech-to-Text service (fast path for API mode)."""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Optional

from synq.stt.base import SpeechToText, TranscriptResult


class ElevenLabsSTT(SpeechToText):
    """Batch STT using ElevenLabs speech_to_text.convert API."""

    def __init__(self, api_key: str, model_id: str = "scribe_v2"):
        from elevenlabs.base_client import BaseElevenLabs

        self.client = BaseElevenLabs(api_key=api_key)
        self.model_id = model_id

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptResult:
        if len(audio_bytes) < 1000:
            return TranscriptResult(text="", confidence=0.0, is_final=True)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            with open(tmp_path, "rb") as f:
                result = self.client.speech_to_text.convert(
                    model_id=self.model_id,
                    file=f,
                    language_code="en",
                    diarize=False,
                    tag_audio_events=False,
                )
            text = (getattr(result, "text", "") or "").strip()
            return TranscriptResult(text=text, confidence=1.0 if text else 0.0, is_final=True)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def start_stream(self) -> None:
        return None

    def process_stream_chunk(self, chunk: bytes) -> Optional[TranscriptResult]:
        return None

    def stop_stream(self) -> Optional[TranscriptResult]:
        return None

