"""pyttsx3 TTS - uses system voices, works offline, no model download."""

from typing import Optional

from synq.tts.base import TextToSpeech


class Pyttsx3TextToSpeech(TextToSpeech):
    """Built-in TTS via pyttsx3 - works on Windows, macOS, Linux."""

    def __init__(self, rate: int = 175, volume: float = 1.0):
        self.rate = rate
        self.volume = volume
        self._engine: Optional[object] = None

    def _ensure_engine(self) -> None:
        if self._engine is None:
            try:
                import pyttsx3
            except ImportError as e:
                raise ImportError(
                    "pyttsx3 required: pip install pyttsx3. "
                    "On Linux you may need: sudo apt-get install espeak"
                ) from e
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)

    def speak(self, text: str, blocking: bool = True) -> None:
        """Speak text. Blocking waits for completion."""
        self._ensure_engine()
        if blocking:
            self._engine.say(text)
            self._engine.runAndWait()
        else:
            self._engine.say(text)
            self._engine.startLoop(False)
            self._engine.iterate()
            self._engine.endLoop()

    def stop(self) -> None:
        """Stop current speech."""
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
