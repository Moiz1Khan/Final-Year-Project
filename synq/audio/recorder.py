"""PyAudio-based recording - FYP style: record until silence."""

import math
import struct
import tempfile
import wave
from pathlib import Path
from typing import Optional

import pyaudio


def get_rms(data: bytes) -> float:
    """Calculate RMS (volume level) of 16-bit PCM audio."""
    count = len(data) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", data)
    sum_squares = sum(s * s for s in shorts)
    return math.sqrt(sum_squares / count)


class PyAudioRecorder:
    """
    Record from microphone until silence - FYP style.
    Uses PyAudio (proven to work).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk: int = 1024,
        silence_threshold: float = 1000,
        silence_duration: float = 1.5,
        device_index: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.device_index = device_index
        self._audio: Optional[pyaudio.PyAudio] = None

    def record_to_file(
        self,
        output_path: Optional[Path] = None,
        prompt: str = "Listening... (speak now, stops after silence)",
    ) -> Optional[Path]:
        """
        Record until silence detected. Returns path to WAV file.
        """
        if output_path is None:
            fd, path = tempfile.mkstemp(suffix=".wav")
            output_path = Path(path)

        self._audio = pyaudio.PyAudio()
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.chunk,
        )

        frames = []
        silent_chunks = 0
        chunks_for_silence = int(self.silence_duration * self.sample_rate / self.chunk)
        has_started = False

        try:
            if prompt:
                print(f"\n{prompt}")
            while True:
                try:
                    data = stream.read(self.chunk, exception_on_overflow=False)
                except OSError:
                    continue
                rms = get_rms(data)

                if rms > self.silence_threshold:
                    has_started = True
                    silent_chunks = 0
                    frames.append(data)
                elif has_started:
                    frames.append(data)
                    silent_chunks += 1
                    if silent_chunks >= chunks_for_silence:
                        break
        except KeyboardInterrupt:
            pass
        finally:
            stream.stop_stream()
            stream.close()
            self._audio.terminate()
            self._audio = None

        if len(frames) == 0:
            return None

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))

        return output_path

    def record_to_bytes(self, prompt: str = "Listening...") -> Optional[bytes]:
        """Record and return raw PCM bytes."""
        path = self.record_to_file(prompt=prompt)
        if path is None:
            return None
        with wave.open(str(path), "rb") as wf:
            return wf.readframes(wf.getnframes())
