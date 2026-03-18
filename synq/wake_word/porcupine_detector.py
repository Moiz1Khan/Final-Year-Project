"""Porcupine wake word detection - precise, low latency. Requires Picovoice setup."""

import struct
from pathlib import Path
from typing import List, Optional, Union

from synq.wake_word.base import WakeWordDetector, WakeWordEvent, WakeWordSource


class PorcupineWakeWordDetector(WakeWordDetector):
    """
    Porcupine-based wake word detection.
    Requires: Picovoice AccessKey + .ppn files for "hey synq", "hi synq", "synq"
    Create at https://console.picovoice.ai
    """

    def __init__(
        self,
        access_key: str,
        keyword_paths: List[Union[str, Path]],
        sample_rate: int = 16000,
    ):
        self.access_key = access_key
        self.keyword_paths = [str(Path(p)) for p in keyword_paths]
        self.sample_rate = sample_rate
        self._porcupine = None
        self._frame_length = 512  # Porcupine expects 512 samples per frame

    def start(self) -> None:
        """Initialize Porcupine engine."""
        try:
            import pvporcupine
        except ImportError as e:
            raise ImportError(
                "pvporcupine is required. Install: pip install pvporcupine"
            ) from e

        self._porcupine = pvporcupine.create(
            access_key=self.access_key,
            keyword_paths=self.keyword_paths,
        )

    def stop(self) -> None:
        """Release Porcupine resources."""
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None

    def process_audio_frame(self, frame: bytes) -> Optional[WakeWordEvent]:
        """
        Process audio frame. Porcupine expects 16-bit PCM, 16kHz, 512 samples/frame.
        """
        if not self._porcupine:
            return None

        if len(frame) < self._frame_length * 2:  # 2 bytes per sample
            return None

        samples = struct.unpack_from("h" * self._frame_length, frame)
        keyword_index = self._porcupine.process(samples)

        if keyword_index >= 0:
            phrases = ["hey synq", "hi synq", "synq"]
            phrase = phrases[keyword_index] if keyword_index < len(phrases) else "synq"
            return WakeWordEvent(
                source=WakeWordSource.VOICE,
                phrase=phrase,
                confidence=1.0,
            )
        return None

    @property
    def preferred_chunk_samples(self) -> int:
        """Porcupine requires exactly 512 samples per frame."""
        return self._frame_length
