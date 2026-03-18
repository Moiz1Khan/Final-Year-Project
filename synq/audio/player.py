"""Pygame-based audio playback with interrupt-on-speech."""

import threading
import time
from pathlib import Path
from typing import Callable, Optional

import pyaudio
import pygame

from synq.audio.recorder import get_rms


class PygamePlayer:
    """
    Play audio files with pygame. Can interrupt playback when user speaks.
    FYP-style: monitor mic during playback, stop if loud speech detected.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk: int = 1024,
        interrupt_threshold: float = 50000,
        interrupt_chunks: int = 3,
    ):
        self.sample_rate = sample_rate
        self.chunk = chunk
        self.interrupt_threshold = interrupt_threshold
        self.interrupt_chunks = interrupt_chunks
        self._playing = False

    def play(self, path: Path, interruptible: bool = True) -> bool:
        """
        Play audio file. If interruptible, stops when user speaks loudly.
        Returns True if played to end, False if interrupted.
        """
        if not path.exists():
            return True

        pygame.mixer.init()
        self._playing = True

        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
        except Exception as e:
            print(f"Playback error: {e}")
            return True

        if not interruptible:
            while pygame.mixer.music.get_busy() and self._playing:
                time.sleep(0.1)
            return True

        # Monitor mic for interrupt
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk,
        )

        loud_chunks = 0
        try:
            while pygame.mixer.music.get_busy() and self._playing:
                try:
                    data = stream.read(self.chunk, exception_on_overflow=False)
                except OSError:
                    time.sleep(0.1)
                    continue
                rms = get_rms(data)
                if rms > self.interrupt_threshold:
                    loud_chunks += 1
                    if loud_chunks >= self.interrupt_chunks:
                        pygame.mixer.music.stop()
                        self._playing = False
                        stream.close()
                        audio.terminate()
                        return False
                else:
                    loud_chunks = 0
                time.sleep(0.05)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            audio.terminate()

        self._playing = False
        return True

    def stop(self) -> None:
        """Stop playback."""
        self._playing = False
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
