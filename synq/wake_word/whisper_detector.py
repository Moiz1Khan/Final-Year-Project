"""Whisper-based wake word detection - better accuracy than Vosk for "hey synq"."""

import re
from collections import deque
from typing import List, Optional

import numpy as np

from synq.wake_word.base import WakeWordDetector, WakeWordEvent, WakeWordSource


class WhisperWakeWordDetector(WakeWordDetector):
    """
    Detects wake word by transcribing buffered audio with Whisper, then matching phrases.
    Uses faster-whisper for better accuracy. Buffers ~1.5-2 sec before each check.
    """

    def __init__(
        self,
        phrases: List[str],
        model_size: str = "tiny",
        sample_rate: int = 16000,
        buffer_seconds: float = 1.2,
        chunk_ms: int = 400,
        device: str = "cpu",
        compute_type: str = "int8",
        debug: bool = False,
    ):
        self.phrases = [p.strip().lower() for p in phrases]
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate
        self.buffer_samples = int(sample_rate * buffer_seconds)
        self.chunk_samples = int(sample_rate * chunk_ms / 1000)
        self.debug = debug
        self._model = None
        self._buffer: deque = deque(maxlen=self.buffer_samples * 2)  # bytes

    def start(self) -> None:
        """Load Whisper model."""
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

    def stop(self) -> None:
        """Release model."""
        self._model = None
        self._buffer.clear()

    def process_audio_frame(self, frame: bytes) -> Optional[WakeWordEvent]:
        """Add frame to buffer; when full, run Whisper and check for wake phrase."""
        if not self._model:
            return None

        self._buffer.extend(frame)

        if len(self._buffer) < self.buffer_samples * 2:
            return None

        audio_bytes = bytes(self._buffer)
        overlap = self.chunk_samples * 2
        self._buffer.clear()
        if len(audio_bytes) > overlap:
            self._buffer.extend(audio_bytes[-overlap:])

        audio_float = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self._model.transcribe(
            audio_float,
            language="en",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=200, speech_pad_ms=50),
        )

        text_parts = []
        for seg in segments:
            text_parts.append(seg.text)
        text = " ".join(text_parts).strip().lower()

        if self.debug and text:
            print(f"[Whisper] {text!r}")

        if text and self._matches_phrase(text):
            return WakeWordEvent(
                source=WakeWordSource.VOICE,
                phrase=text,
                confidence=1.0,
                full_transcript=text,
            )
        return None

    def _matches_phrase(self, text: str) -> bool:
        """Check if transcribed text matches any wake phrase."""
        if not text:
            return False
        text = text.strip().lower()
        text = re.sub(r"\s+", " ", text)
        for phrase in self.phrases:
            if phrase in text or text in phrase:
                return True
            if self._normalized_match(text, phrase):
                return True
        return False

    def _normalized_match(self, text: str, phrase: str) -> bool:
        """Fuzzy match - handles 'synq' vs 'sync' etc."""
        text_norm = re.sub(r"[^a-z\s]", "", text)
        phrase_norm = re.sub(r"[^a-z\s]", "", phrase)
        return phrase_norm in text_norm or text_norm.endswith(phrase_norm)
