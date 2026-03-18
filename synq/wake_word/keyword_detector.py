"""Keyword-based wake word detection - Vosk/Whisper + phrase matching. Works offline."""

import json
import re
from pathlib import Path
from typing import List, Optional

from synq.wake_word.base import WakeWordDetector, WakeWordEvent, WakeWordSource


class KeywordWakeWordDetector(WakeWordDetector):
    """
    Detects wake word by matching transcribed speech against configured phrases.
    Uses Vosk for offline STT. Phrases like "hey synq", "hi synq", "synq".
    """

    def __init__(
        self,
        phrases: List[str],
        model_path: str,
        sample_rate: int = 16000,
        debug: bool = False,
    ):
        self.phrases = [p.strip().lower() for p in phrases]
        self.model_path = Path(model_path)
        self.sample_rate = sample_rate
        self.debug = debug
        self._model = None
        self._recognizer = None

    def start(self) -> None:
        """Load Vosk model and create recognizer."""
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError as e:
            raise ImportError(
                "Vosk is required for keyword wake word. Install: pip install vosk"
            ) from e

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Vosk model not found at {self.model_path}. "
                f"Download from https://alphacephei.com/vosk/models "
                f"(e.g. vosk-model-small-en-us-0.15)"
            )

        self._model = Model(str(self.model_path))
        self._recognizer = KaldiRecognizer(self._model, self.sample_rate)

    def stop(self) -> None:
        """Release model resources."""
        self._recognizer = None
        self._model = None

    def process_audio_frame(self, frame: bytes) -> Optional[WakeWordEvent]:
        """
        Process audio frame through Vosk. Check partial and final results
        for wake phrase match.
        """
        if not self._recognizer:
            return None

        if self._recognizer.AcceptWaveform(frame):
            result = json.loads(self._recognizer.Result())
            text = result.get("text", "").strip().lower()
            if self.debug and text:
                print(f"[Vosk] final: {text!r}")
            if self._matches_phrase(text):
                return WakeWordEvent(
                    source=WakeWordSource.VOICE,
                    phrase=text,
                    confidence=1.0,
                    full_transcript=text,
                )
        else:
            partial = json.loads(self._recognizer.PartialResult())
            text = partial.get("partial", "").strip().lower()
            if self.debug and text:
                print(f"[Vosk] partial: {text!r}")
            if text and self._matches_phrase(text):
                return WakeWordEvent(
                    source=WakeWordSource.VOICE,
                    phrase=text,
                    confidence=0.9,
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
