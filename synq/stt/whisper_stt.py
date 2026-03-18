"""Whisper-based Speech-to-Text - high accuracy, offline."""

from pathlib import Path
from typing import Optional

import numpy as np

from synq.stt.base import SpeechToText, TranscriptResult


class WhisperSpeechToText(SpeechToText):
    """faster-whisper STT - better accuracy than Vosk."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        sample_rate: int = 16000,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate
        self._model = None

    def _ensure_loaded(self) -> None:
        """Lazy load faster-whisper model."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise ImportError(
                    "faster-whisper required: pip install faster-whisper"
                ) from e

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )

    def _bytes_to_float(self, audio_bytes: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 for Whisper."""
        arr = np.frombuffer(audio_bytes, dtype=np.int16)
        return arr.astype(np.float32) / 32768.0

    def transcribe(self, audio_bytes: bytes, sample_rate: int) -> TranscriptResult:
        """Transcribe full audio buffer."""
        self._ensure_loaded()

        if len(audio_bytes) < 1000:
            return TranscriptResult(text="", confidence=0.0, is_final=True)

        audio_float = self._bytes_to_float(audio_bytes)
        segments, info = self._model.transcribe(
            audio_float,
            language="en",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=100),
        )

        text_parts = []
        for seg in segments:
            text_parts.append(seg.text)
        text = " ".join(text_parts).strip()

        return TranscriptResult(
            text=text,
            confidence=1.0 if text else 0.0,
            is_final=True,
        )

    def start_stream(self) -> None:
        """Whisper is batch-based; no streaming."""
        self._ensure_loaded()

    def process_stream_chunk(self, chunk: bytes) -> Optional[TranscriptResult]:
        """Whisper doesn't support streaming; use transcribe() on full audio."""
        return None

    def stop_stream(self) -> Optional[TranscriptResult]:
        """Whisper doesn't support streaming."""
        return None
