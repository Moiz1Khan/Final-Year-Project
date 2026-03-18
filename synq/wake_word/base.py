"""Base classes for wake word detection - designed for voice and future face recognition."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WakeWordSource(Enum):
    """Source that triggered the wake word - for future face recognition integration."""
    VOICE = "voice"
    FACE = "face"  # Future: face recognition as wake trigger


@dataclass
class WakeWordEvent:
    """Event emitted when wake word is detected."""
    source: WakeWordSource
    phrase: str
    confidence: float = 1.0
    # Full transcript when available (e.g. "hey synq what time is it") - command follows wake
    full_transcript: Optional[str] = None


class WakeWordDetector(ABC):
    """
    Abstract base for wake word detectors.
    
    Design supports multiple triggers:
    - Voice: "hey synq", "hi synq", "synq"
    - Future: Face recognition (e.g., when recognized user looks at device)
    """

    @property
    def preferred_chunk_samples(self) -> Optional[int]:
        """Override to specify required samples per frame (e.g. Porcupine=512)."""
        return None

    @abstractmethod
    def start(self) -> None:
        """Start listening for wake word."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release resources."""
        ...

    @abstractmethod
    def process_audio_frame(self, frame: bytes) -> Optional[WakeWordEvent]:
        """
        Process audio frame. Returns WakeWordEvent if wake word detected.
        
        For voice: frame is raw PCM audio bytes.
        For face (future): could accept image/video frame.
        """
        ...

    def trigger_wake(self, source: WakeWordSource = WakeWordSource.VOICE) -> WakeWordEvent:
        """Manual wake trigger - e.g., from face recognition module."""
        return WakeWordEvent(source=source, phrase="manual", confidence=1.0)
