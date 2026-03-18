"""Vosk-based Speech-to-Text - offline, lightweight."""

import json
from pathlib import Path
from typing import Optional

from synq.stt.base import SpeechToText, TranscriptResult


class VoskSpeechToText(SpeechToText):
    """Vosk STT - works fully offline."""

    def __init__(self, model_path: str, sample_rate: int = 16000):
        self.model_path = Path(model_path)
        self.sample_rate = sample_rate
        self._model = None
        self._recognizer = None

    def _ensure_loaded(self) -> None:
        """Lazy load model."""
        if self._model is None:
            try:
                from vosk import Model, KaldiRecognizer
            except ImportError as e:
                raise ImportError("Vosk required: pip install vosk") from e

            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"Vosk model not found: {self.model_path}. "
                    "Download from https://alphacephei.com/vosk/models"
                )
            self._model = Model(str(self.model_path))
            self._recognizer = KaldiRecognizer(self._model, self.sample_rate)

    def transcribe(self, audio_bytes: bytes, sample_rate: int) -> TranscriptResult:
        """Transcribe full audio buffer."""
        self._ensure_loaded()
        self._recognizer = KaldiRecognizer(self._model, sample_rate)

        self._recognizer.AcceptWaveform(audio_bytes)
        result = json.loads(self._recognizer.FinalResult())
        text = result.get("text", "").strip()
        return TranscriptResult(
            text=text,
            confidence=1.0 if text else 0.0,
            is_final=True,
        )

    def start_stream(self) -> None:
        """Start streaming - creates fresh recognizer."""
        self._ensure_loaded()
        self._recognizer = KaldiRecognizer(self._model, self.sample_rate)

    def process_stream_chunk(self, chunk: bytes) -> Optional[TranscriptResult]:
        """Process chunk, return result if utterance complete."""
        if not self._recognizer:
            return None

        if self._recognizer.AcceptWaveform(chunk):
            result = json.loads(self._recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                return TranscriptResult(text=text, confidence=1.0, is_final=True)
        return None

    def stop_stream(self) -> Optional[TranscriptResult]:
        """Get final result from stream."""
        if not self._recognizer:
            return None
        result = json.loads(self._recognizer.FinalResult())
        text = result.get("text", "").strip()
        return TranscriptResult(
            text=text,
            confidence=1.0 if text else 0.0,
            is_final=True,
        )
