"""
Synq TTS: pyttsx3 for text-to-speech generation, pygame for playback.
pyttsx3 generates the audio file, pygame plays it (enables interrupt-on-speech).
"""

import tempfile
from pathlib import Path
from typing import Optional

from synq.audio.player import PygamePlayer
from synq.tts.base import TextToSpeech


class SynqTTS(TextToSpeech):
    """
    Best of both: pyttsx3 (offline TTS, good voices) + pygame (playback with interrupt).
    """

    def __init__(
        self,
        rate: int = 175,
        volume: float = 1.0,
        interrupt_threshold: float = 50000,
        interrupt_chunks: int = 3,
    ):
        self.rate = rate
        self.volume = volume
        self.player = PygamePlayer(
            interrupt_threshold=interrupt_threshold,
            interrupt_chunks=interrupt_chunks,
        )
        self._engine = None

    def _ensure_engine(self) -> None:
        if self._engine is None:
            try:
                import pyttsx3
            except ImportError as e:
                raise ImportError("pyttsx3 required: pip install pyttsx3") from e
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)

    def speak(self, text: str, blocking: bool = True, interruptible: bool = True) -> bool:
        """
        Speak text. Uses pyttsx3 to generate, pygame to play.
        If interruptible and user speaks, playback stops.
        Returns False if interrupted, True if played to end.
        """
        self._ensure_engine()
        if not text.strip():
            return True

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = Path(f.name)
        self._engine.save_to_file(text, str(path))

        try:
            self._engine.runAndWait()
            if not path.exists():
                return True
            return self.player.play(path, interruptible=interruptible)
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def stop(self) -> None:
        """Stop playback."""
        self.player.stop()
