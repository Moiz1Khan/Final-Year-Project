"""
ElevenLabs TTS - low-latency streaming.
PCM output = play chunks as they arrive (no decode wait).
optimize_streaming_latency=4 = minimum delay.
"""

import threading
import time
from queue import Empty, Queue
from typing import Optional

import numpy as np
import pyaudio
import sounddevice as sd

from synq.audio.recorder import get_rms


class ElevenLabsTTS:
    """
    ElevenLabs streaming TTS - plays audio as it's generated.
    Like professional voice agents ( ElevenLabs Conversational AI).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_flash_v2_5",
        optimize_streaming_latency: int = 4,
        sample_rate: int = 16000,
        interrupt_threshold: float = 50000,
        interrupt_chunks: int = 3,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.optimize_streaming_latency = optimize_streaming_latency
        self.sample_rate = sample_rate
        self.interrupt_threshold = interrupt_threshold
        self.interrupt_chunks = interrupt_chunks
        self._playing = False
        self.last_metrics = {
            "first_byte_ms": 0,
            "playback_ms": 0,
        }

    def speak(
        self,
        text: str,
        blocking: bool = True,
        interruptible: bool = True,
    ) -> bool:
        """Stream TTS, play PCM chunks as they arrive. Returns False if interrupted."""
        if not text.strip():
            return True

        try:
            from elevenlabs.base_client import BaseElevenLabs
        except ImportError:
            raise ImportError("elevenlabs required: pip install elevenlabs")

        # BaseElevenLabs has TextToSpeechClient.convert() (streaming).
        # The main ElevenLabs client overrides text_to_speech with RealtimeTextToSpeechClient.
        client = BaseElevenLabs(api_key=self.api_key)
        self._playing = True
        interrupted = [False]
        first_byte_seen = [False]
        t_play_start = time.perf_counter()
        t_playback_start = [None]
        self.last_metrics = {"first_byte_ms": 0, "playback_ms": 0}

        def stream_and_play():
            try:
                stream = client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    text=text,
                    model_id=self.model_id,
                    output_format="pcm_16000",
                    optimize_streaming_latency=self.optimize_streaming_latency,
                )
                with sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype=np.int16,
                    blocksize=1024,
                ) as out:
                    for chunk in stream:
                        if not self._playing or interrupted[0]:
                            break
                        if chunk:
                            if not first_byte_seen[0]:
                                first_byte_seen[0] = True
                                self.last_metrics["first_byte_ms"] = int((time.perf_counter() - t_play_start) * 1000)
                                t_playback_start[0] = time.perf_counter()
                            arr = np.frombuffer(chunk, dtype=np.int16)
                            out.write(arr)
            except Exception as e:
                print(f"[ElevenLabs Error] {e}")

        play_thread = threading.Thread(target=stream_and_play)
        play_thread.start()

        if interruptible:
            p = pyaudio.PyAudio()
            mic = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
            )
            loud = 0
            while play_thread.is_alive() and self._playing:
                try:
                    d = mic.read(1024, exception_on_overflow=False)
                    if get_rms(d) > self.interrupt_threshold:
                        loud += 1
                        if loud >= self.interrupt_chunks:
                            interrupted[0] = True
                            self._playing = False
                            break
                    else:
                        loud = 0
                except Exception:
                    pass
                time.sleep(0.03)
            mic.close()
            p.terminate()

        play_thread.join(timeout=30)
        self._playing = False
        if t_playback_start[0] is not None:
            self.last_metrics["playback_ms"] = int((time.perf_counter() - t_playback_start[0]) * 1000)
        return not interrupted[0]

    def stop(self) -> None:
        self._playing = False
