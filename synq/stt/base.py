"""Base Speech-to-Text interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TranscriptResult:
    """Result from speech recognition."""
    text: str
    confidence: float
    is_final: bool


class SpeechToText(ABC):
    """Abstract base for speech-to-text engines."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, sample_rate: int) -> TranscriptResult:
        """Transcribe audio to text."""
        ...

    @abstractmethod
    def start_stream(self) -> None:
        """Start streaming recognition (if supported)."""
        ...

    @abstractmethod
    def process_stream_chunk(self, chunk: bytes) -> Optional[TranscriptResult]:
        """Process a chunk of streaming audio."""
        ...

    @abstractmethod
    def stop_stream(self) -> Optional[TranscriptResult]:
        """Stop stream and get final result."""
        ...
