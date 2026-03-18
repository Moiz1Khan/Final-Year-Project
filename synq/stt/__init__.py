"""Speech-to-Text module."""

from synq.stt.base import SpeechToText
from synq.stt.vosk_stt import VoskSpeechToText

__all__ = ["SpeechToText", "VoskSpeechToText"]
