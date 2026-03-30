"""
Realtime voice agent (low-latency architecture).

Design goals:
- Preserve existing business logic: still uses Orchestrator.process(...)
- Reduce perceived delay via shorter endpointing + immediate playback path
- Support interruption (barge-in) while assistant is speaking
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import pyaudio

from synq.audio.recorder import get_rms
from synq.audio.realtime_player import RealtimePlayer
from synq.stt.base import SpeechToText, TranscriptResult


@dataclass
class RealtimeConfig:
    sample_rate: int = 16000
    chunk_ms: int = 40
    endpoint_silence_ms: int = 350
    min_utterance_ms: int = 250
    vad_threshold: float = 900.0
    execute_on_final_only: bool = True


class RealtimeVoiceAgent:
    def __init__(
        self,
        *,
        stt: SpeechToText,
        orchestrator,
        tts,
        config: RealtimeConfig,
        device_index: Optional[int] = None,
        debug: bool = False,
        active_user_id: int = 1,
    ):
        self.stt = stt
        self.orchestrator = orchestrator
        self.tts = tts
        self.cfg = config
        self.device_index = device_index
        self.debug = debug
        self.active_user_id = active_user_id
        self._running = False
        self._assistant_speaking = False
        self._player = RealtimePlayer(sample_rate=self.cfg.sample_rate)

    def _metrics_print(self, metrics: dict) -> None:
        if not self.debug:
            return
        parts = []
        base = metrics.get("t_start")
        for key in ["t_eos", "t_stt_done", "t_reply_start", "t_reply_end"]:
            if key in metrics and base:
                parts.append(f"{key[2:]}={int((metrics[key]-base)*1000)}ms")
        if parts:
            print("[RealtimeMetrics]", ", ".join(parts))

    def stop(self) -> None:
        self._running = False
        self._assistant_speaking = False
        try:
            self.tts.stop()
        except Exception:
            pass
        self._player.stop()

    def _capture_utterance(self, stream) -> Optional[bytes]:
        chunk = int(self.cfg.sample_rate * (self.cfg.chunk_ms / 1000.0))
        silence_chunks_needed = max(1, int(self.cfg.endpoint_silence_ms / self.cfg.chunk_ms))
        min_chunks = max(1, int(self.cfg.min_utterance_ms / self.cfg.chunk_ms))

        frames = []
        in_speech = False
        silent_chunks = 0
        speech_chunks = 0

        while self._running:
            data = stream.read(chunk, exception_on_overflow=False)
            rms = get_rms(data)

            # Barge-in: user speech while assistant talking
            if self._assistant_speaking and rms > self.cfg.vad_threshold:
                try:
                    self.tts.stop()
                except Exception:
                    pass
                self._assistant_speaking = False

            if rms > self.cfg.vad_threshold:
                in_speech = True
                silent_chunks = 0
                speech_chunks += 1
                frames.append(data)
            elif in_speech:
                silent_chunks += 1
                frames.append(data)
                if silent_chunks >= silence_chunks_needed and speech_chunks >= min_chunks:
                    break

        if not frames:
            return None
        return b"".join(frames)

    def run(self) -> None:
        self._running = True
        print("=" * 50)
        print("Synq Realtime Voice Agent")
        print("=" * 50)
        print("Mode: REALTIME (logic preserved)")
        print(f"Active user id: {self.active_user_id}")
        print("Press Ctrl+C to exit\n")

        p = pyaudio.PyAudio()
        chunk = int(self.cfg.sample_rate * (self.cfg.chunk_ms / 1000.0))
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.cfg.sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=chunk,
        )

        try:
            while self._running:
                print("\n[READY] Listening...")
                metrics = {"t_start": time.time()}
                pcm = self._capture_utterance(stream)
                if not pcm or len(pcm) < 800:
                    continue
                metrics["t_eos"] = time.time()

                # Keep existing STT implementation in first migration phase
                result = self.stt.transcribe(pcm, self.cfg.sample_rate)
                metrics["t_stt_done"] = time.time()
                text = (result.text or "").strip() if result else ""
                if not text:
                    continue

                print(f"[HEARD] \"{text}\"")
                response = self.orchestrator.process(
                    TranscriptResult(text=text, confidence=1.0, is_final=True),
                    user_id=self.active_user_id,
                )
                print(f"[REPLY] {response}")
                metrics["t_reply_start"] = time.time()

                self._assistant_speaking = True
                try:
                    self.tts.speak(response, interruptible=True)
                finally:
                    self._assistant_speaking = False
                metrics["t_reply_end"] = time.time()
                self._metrics_print(metrics)
        except KeyboardInterrupt:
            print("\n\n[Synq] Stopping realtime agent...")
        finally:
            self.stop()
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            p.terminate()

