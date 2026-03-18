"""Base Text-to-Speech interface."""

from abc import ABC, abstractmethod


class TextToSpeech(ABC):
    """Abstract base for TTS engines."""

    @abstractmethod
    def speak(self, text: str, blocking: bool = True) -> None:
        """Speak the given text. If blocking, wait until done."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop current speech."""
        ...
