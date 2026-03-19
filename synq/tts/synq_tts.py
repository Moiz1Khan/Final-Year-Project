"""
Synq TTS: pyttsx3 for text-to-speech generation, pygame for playback.
pyttsx3 generates the audio file, pygame plays it (enables interrupt-on-speech).

Note: pyttsx3 runAndWait() is known to block/stop after first use on Windows.
We create a fresh engine per speak to avoid this.
"""

import tempfile
import time
from pathlib import Path
from typing import Optional

from synq.audio.player import PygamePlayer
from synq.tts.base import TextToSpeech


class SynqTTS(TextToSpeech):
    """
    Best of both: pyttsx3 (offline TTS, good voices) + pygame (playback with interrupt).
    Uses fresh pyttsx3 engine per speak to avoid Windows runAndWait() stuck-after-first-use bug.
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

    def _create_engine(self):
        """Create a fresh pyttsx3 engine. Must be disposed after use."""
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        return engine

    def speak(self, text: str, blocking: bool = True, interruptible: bool = True) -> bool:
        """
        Speak text. Uses pyttsx3 to generate, pygame to play.
        If interruptible and user speaks, playback stops.
        Returns False if interrupted, True if played to end.
        """
        if not text.strip():
            return True

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = Path(f.name)

        engine = self._create_engine()
        try:
            engine.save_to_file(text, str(path))
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass
            del engine

        try:
            if not path.exists():
                return True
            result = self.player.play(path, interruptible=interruptible)
            # Brief delay so Windows can release mic before next record
            time.sleep(0.35)
            return result
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def stop(self) -> None:
        """Stop playback."""
        self.player.stop()
