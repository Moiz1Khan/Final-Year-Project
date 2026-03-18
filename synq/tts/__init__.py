"""Text-to-Speech module."""

from synq.tts.base import TextToSpeech
from synq.tts.pyttsx3_tts import Pyttsx3TextToSpeech

__all__ = ["TextToSpeech", "Pyttsx3TextToSpeech"]
