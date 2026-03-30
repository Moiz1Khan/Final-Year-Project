"""
Low-latency streaming PCM player for realtime mode.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import sounddevice as sd


class RealtimePlayer:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._stream: Optional[sd.OutputStream] = None
        self._playing = False

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.int16,
            blocksize=1024,
        )
        self._stream.start()
        self._playing = True

    def write_pcm16(self, chunk: bytes) -> None:
        if self._stream is None:
            self.start()
        if not chunk:
            return
        arr = np.frombuffer(chunk, dtype=np.int16)
        if arr.size > 0 and self._stream is not None:
            self._stream.write(arr)

    def stop(self) -> None:
        self._playing = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

