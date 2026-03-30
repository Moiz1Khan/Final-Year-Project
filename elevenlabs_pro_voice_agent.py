"""
Standalone ElevenLabs voice agent (root-level script).

Architecture (production-style pipeline):
  Mic Capture (VAD) -> STT (ElevenLabs) -> NLU/Logic -> Streaming TTS (ElevenLabs)

Why this file exists:
- User requested a new standalone voice agent outside project folders.
- Uses ElevenLabs API for speech services.
- Keeps code isolated from existing Synq modules.

Environment variables:
  ELEVENLABS_API_KEY          (required)
  ELEVENLABS_VOICE_ID         (required/strongly recommended)
  ELEVENLABS_TTS_MODEL_ID     (optional, default: eleven_flash_v2_5)
  ELEVENLABS_STT_MODEL_ID     (optional, default: scribe_v2)
"""

from __future__ import annotations

import math
import os
import struct
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pyaudio
import sounddevice as sd
from dotenv import load_dotenv


def get_rms(data: bytes) -> float:
    count = len(data) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", data)
    sum_squares = sum(s * s for s in shorts)
    return math.sqrt(sum_squares / count)


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    chunk: int = 1024
    silence_threshold: float = 1000.0
    silence_duration_s: float = 0.6
    min_utterance_bytes: int = 2000
    interrupt_threshold: float = 50000.0
    interrupt_chunks: int = 3
    input_device_index: Optional[int] = None


class VADRecorder:
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg

    def record_until_silence(self, prompt: str = "[LISTENING] Speak now...") -> Optional[bytes]:
        print(prompt)
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.cfg.sample_rate,
            input=True,
            input_device_index=self.cfg.input_device_index,
            frames_per_buffer=self.cfg.chunk,
        )
        frames = []
        started = False
        silent_chunks = 0
        max_silent = int(self.cfg.silence_duration_s * self.cfg.sample_rate / self.cfg.chunk)
        try:
            while True:
                data = stream.read(self.cfg.chunk, exception_on_overflow=False)
                rms = get_rms(data)
                if rms > self.cfg.silence_threshold:
                    started = True
                    silent_chunks = 0
                    frames.append(data)
                elif started:
                    frames.append(data)
                    silent_chunks += 1
                    if silent_chunks >= max_silent:
                        break
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        if not frames:
            return None
        pcm = b"".join(frames)
        if len(pcm) < self.cfg.min_utterance_bytes:
            return None
        return pcm


class ElevenLabsSTT:
    def __init__(self, api_key: str, model_id: str = "scribe_v2", sample_rate: int = 16000):
        from elevenlabs.base_client import BaseElevenLabs

        self.client = BaseElevenLabs(api_key=api_key)
        self.model_id = model_id
        self.sample_rate = sample_rate

    def transcribe_pcm16(self, pcm16: bytes) -> str:
        # Eleven STT expects a file-like input. We wrap PCM in WAV.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(pcm16)

            with open(tmp_path, "rb") as f:
                result = self.client.speech_to_text.convert(
                    model_id=self.model_id,
                    file=f,
                    language_code="en",
                    diarize=False,
                    tag_audio_events=False,
                )
            # SDK response object has `text` for synchronous transcription.
            text = (getattr(result, "text", "") or "").strip()
            return text
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


class ElevenLabsStreamingTTS:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_flash_v2_5",
        sample_rate: int = 16000,
        optimize_streaming_latency: int = 4,
        interrupt_threshold: float = 50000.0,
        interrupt_chunks: int = 3,
    ):
        from elevenlabs.base_client import BaseElevenLabs

        self.client = BaseElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.optimize_streaming_latency = optimize_streaming_latency
        self.interrupt_threshold = interrupt_threshold
        self.interrupt_chunks = interrupt_chunks
        self._playing = False

    def speak(self, text: str, interruptible: bool = True) -> bool:
        if not text.strip():
            return True

        interrupted = [False]
        self._playing = True

        def _play():
            try:
                audio_stream = self.client.text_to_speech.convert(
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
                    for chunk in audio_stream:
                        if not self._playing or interrupted[0]:
                            break
                        if chunk:
                            out.write(np.frombuffer(chunk, dtype=np.int16))
            except Exception as e:
                print(f"[TTS Error] {e}")

        t = threading.Thread(target=_play, daemon=True)
        t.start()

        if interruptible:
            p = pyaudio.PyAudio()
            mic = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=1024,
            )
            loud = 0
            try:
                while t.is_alive() and self._playing:
                    d = mic.read(1024, exception_on_overflow=False)
                    if get_rms(d) > self.interrupt_threshold:
                        loud += 1
                        if loud >= self.interrupt_chunks:
                            interrupted[0] = True
                            self._playing = False
                            break
                    else:
                        loud = 0
                    time.sleep(0.03)
            finally:
                mic.close()
                p.terminate()

        t.join(timeout=30)
        self._playing = False
        return not interrupted[0]

    def stop(self) -> None:
        self._playing = False


class IntentLogic:
    """
    Lightweight logic layer.
    Replace with your own business logic/tool-calling if needed.
    """

    def respond(self, text: str) -> str:
        t = text.lower().strip()
        if not t:
            return "I didn't catch that. Could you repeat?"
        if "time" in t:
            return f"The current time is {time.strftime('%I:%M %p')}."
        if "date" in t or "day" in t:
            return f"Today is {time.strftime('%A, %B %d, %Y')}."
        if any(x in t for x in ["hello", "hi", "hey"]):
            return "Hello. I can help you. Ask me anything."
        if "stop" in t or "goodbye" in t or "bye" in t:
            return "__EXIT__"
        return (
            "I heard you. For full assistant actions, connect this script's logic "
            "to your task, calendar, and email tools."
        )


class ElevenLabsProVoiceAgent:
    def __init__(self, audio_cfg: AudioConfig):
        load_dotenv()
        api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        tts_model = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_flash_v2_5").strip()
        stt_model = os.getenv("ELEVENLABS_STT_MODEL_ID", "scribe_v2").strip()

        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is missing in environment.")
        if not voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID is missing in environment.")

        self.audio_cfg = audio_cfg
        self.recorder = VADRecorder(audio_cfg)
        self.stt = ElevenLabsSTT(api_key=api_key, model_id=stt_model, sample_rate=audio_cfg.sample_rate)
        self.tts = ElevenLabsStreamingTTS(
            api_key=api_key,
            voice_id=voice_id,
            model_id=tts_model,
            sample_rate=audio_cfg.sample_rate,
            optimize_streaming_latency=4,
            interrupt_threshold=audio_cfg.interrupt_threshold,
            interrupt_chunks=audio_cfg.interrupt_chunks,
        )
        self.logic = IntentLogic()

    def run(self) -> None:
        print("=" * 60)
        print("ElevenLabs Pro Voice Agent (Standalone)")
        print("=" * 60)
        print("Say 'stop' or 'goodbye' to exit.\n")

        while True:
            try:
                pcm = self.recorder.record_until_silence()
                if not pcm:
                    continue

                t0 = time.time()
                text = self.stt.transcribe_pcm16(pcm)
                t1 = time.time()
                if not text:
                    continue
                print(f"[HEARD] \"{text}\"")
                print(f"[LATENCY] STT={int((t1-t0)*1000)}ms")

                reply = self.logic.respond(text)
                if reply == "__EXIT__":
                    self.tts.speak("Goodbye.")
                    print("[EXIT] Bye.")
                    break

                print(f"[REPLY] {reply}")
                t2 = time.time()
                self.tts.speak(reply, interruptible=True)
                t3 = time.time()
                print(f"[LATENCY] NLU={int((t2-t1)*1000)}ms, TTS={int((t3-t2)*1000)}ms")
            except KeyboardInterrupt:
                print("\n[EXIT] Stopped by user.")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(0.2)


def main() -> None:
    cfg = AudioConfig()
    agent = ElevenLabsProVoiceAgent(cfg)
    agent.run()


if __name__ == "__main__":
    main()

