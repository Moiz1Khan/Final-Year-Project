"""Wake word detection - supports voice and will support face recognition later."""

from synq.wake_word.base import WakeWordDetector, WakeWordEvent
from synq.wake_word.keyword_detector import KeywordWakeWordDetector
from synq.wake_word.porcupine_detector import PorcupineWakeWordDetector

__all__ = [
    "WakeWordDetector",
    "WakeWordEvent",
    "KeywordWakeWordDetector",
    "PorcupineWakeWordDetector",
]
