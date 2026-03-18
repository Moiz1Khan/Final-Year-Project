"""API-based TTS - OpenAI TTS + pygame playback."""

from pathlib import Path
from typing import Optional

from synq.audio.player import PygamePlayer
from synq.tts.base import TextToSpeech


class ApiTTS(TextToSpeech):
    """OpenAI TTS API + pygame playback. Production quality."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "tts-1",
        voice: str = "alloy",
        interrupt_threshold: float = 50000,
        interrupt_chunks: int = 3,
    ):
        from synq.services.openai_tts import OpenAITTS
        self._openai_tts = OpenAITTS(api_key=api_key, model=model, voice=voice)
        self.player = PygamePlayer(
            interrupt_threshold=interrupt_threshold,
            interrupt_chunks=interrupt_chunks,
        )

    def speak(self, text: str, blocking: bool = True, interruptible: bool = True) -> bool:
        if not text.strip():
            return True
        try:
            path = self._openai_tts.speak_to_file(text)
            try:
                return self.player.play(path, interruptible=interruptible)
            finally:
                path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[TTS Error] {e}")
            return True

    def stop(self) -> None:
        self.player.stop()
