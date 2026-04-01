"""
Voice agent using shared Synq API (JWT): transcribe → chat → TTS on server.
Client holds no OpenAI/ElevenLabs keys; authenticate with auth_token.json from web login.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
import pyaudio
import sounddevice as sd

from synq.audio.recorder import PyAudioRecorder, get_rms
from synq.services.synq_cloud_client import SynqCloudClient
from synq.context_monitoring.voice_snapshot import (
    build_voice_context_injection,
    looks_like_desktop_fact_question,
)
from synq.skills.desktop_skill import DESKTOP_SKILL_FALLBACK_REPLY, DesktopSkill


class RemoteVoiceAgent:
    def __init__(
        self,
        *,
        client: SynqCloudClient,
        recorder: PyAudioRecorder,
        device_index: Optional[int] = None,
        debug: bool = False,
        active_user_id: int = 1,
        interrupt_threshold: float = 50000.0,
        interrupt_chunks: int = 3,
    ):
        self.client = client
        self.recorder = recorder
        self.device_index = device_index
        self.debug = debug
        self.active_user_id = active_user_id
        self.interrupt_threshold = interrupt_threshold
        self.interrupt_chunks = interrupt_chunks
        self._running = False
        self._playing = False

    def stop(self) -> None:
        self._running = False
        self._playing = False

    def _record_pcm(self) -> tuple[Optional[bytes], Optional[dict]]:
        print("[RECORDING] Speak now. Will stop after silence...")
        timings = {"capture_ms": 0, "stt_ms": 0}
        t0 = time.perf_counter()
        chunk = self.recorder.chunk
        sample_rate = self.recorder.sample_rate
        silence_threshold = self.recorder.silence_threshold
        silence_duration = self.recorder.silence_duration
        max_silent = int(silence_duration * sample_rate / chunk)

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=chunk,
        )
        frames = []
        started = False
        silent_chunks = 0
        chunks_no_speech = 0
        max_wait_chunks = int(
            self.recorder.max_wait_speech_seconds * sample_rate / chunk
        )
        max_total_chunks = int(self.recorder.max_record_seconds * sample_rate / chunk)
        total_chunks = 0
        last_hint_chunk = 0
        try:
            while self._running:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                except OSError:
                    continue
                rms = get_rms(data)
                total_chunks += 1
                if rms > silence_threshold:
                    started = True
                    silent_chunks = 0
                    chunks_no_speech = 0
                    frames.append(data)
                elif started:
                    frames.append(data)
                    silent_chunks += 1
                    if silent_chunks >= max_silent:
                        break
                else:
                    chunks_no_speech += 1
                    if (
                        chunks_no_speech >= last_hint_chunk + int(15 * sample_rate / chunk)
                        and chunks_no_speech < max_wait_chunks
                    ):
                        print(
                            "[LISTEN] Still waiting for speech... "
                            "(wrong mic, quiet room, or silence_threshold too high - see config audio.*)"
                        )
                        last_hint_chunk = chunks_no_speech
                    if chunks_no_speech >= max_wait_chunks:
                        print(
                            "[WARN] No speech detected before timeout. "
                            "Set audio.device to your mic index, or lower audio.silence_threshold."
                        )
                        break
                if started and total_chunks >= max_total_chunks:
                    print("[WARN] Max recording length reached; stopping.")
                    break
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        if not frames:
            print("[WARN] No audio recorded")
            return None, None
        pcm = b"".join(frames)
        timings["capture_ms"] = int((time.perf_counter() - t0) * 1000)
        if len(pcm) < 2000:
            print("[WARN] Audio too short")
            return None, None
        return pcm, timings

    def _speak_pcm(self, pcm: bytes, sample_rate: int) -> bool:
        if not pcm:
            return True
        interrupted = [False]
        self._playing = True

        def _play():
            try:
                arr = np.frombuffer(pcm, dtype=np.int16)
                with sd.OutputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype=np.int16,
                    blocksize=1024,
                ) as out:
                    # chunk writes
                    step = 1024 * 2
                    for i in range(0, len(arr), 1024):
                        if not self._playing or interrupted[0]:
                            break
                        chunk = arr[i : i + 1024]
                        if len(chunk):
                            out.write(chunk)
            except Exception as e:
                print(f"[Remote TTS play] {e}")

        t = threading.Thread(target=_play, daemon=True)
        t.start()

        p = pyaudio.PyAudio()
        mic = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=1024,
        )
        loud = 0
        try:
            while t.is_alive() and self._playing:
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
        finally:
            mic.close()
            p.terminate()
        t.join(timeout=60)
        self._playing = False
        return not interrupted[0]

    def run(self) -> None:
        self._running = True
        print("=" * 50)
        print("Synq Voice Agent (Synq Cloud API)")
        print("=" * 50)
        print(f"Active user id: {self.active_user_id}")
        print(
            "STT + NLU + TTS use the API (JWT); desktop actions run on this PC. "
            "Screen/window questions include a local snapshot so answers match what is open."
        )
        print("Press Ctrl+C to exit\n")

        try:
            while self._running:
                time.sleep(0.05)
                print("\n[READY] Listening for command...")
                pcm, timings = self._record_pcm()
                if not pcm or not timings:
                    continue
                t_stt = time.perf_counter()
                try:
                    text = self.client.transcribe_pcm16_wav(pcm, self.recorder.sample_rate)
                except Exception as e:
                    print(f"[API STT Error] {e}")
                    continue
                timings["stt_ms"] = int((time.perf_counter() - t_stt) * 1000)
                if not text:
                    continue
                print(f"[HEARD] \"{text}\"")
                t_logic = time.perf_counter()
                try:
                    local = DesktopSkill().handle("desktop_action", {}, text.strip())
                    if local.response != DESKTOP_SKILL_FALLBACK_REPLY:
                        reply = local.response
                    elif looks_like_desktop_fact_question(text):
                        reply = self.client.chat(
                            f"{build_voice_context_injection()}\n\nUser question: {text}"
                        )
                    else:
                        reply = self.client.chat(text)
                except Exception as e:
                    print(f"[API Chat Error] {e}")
                    continue
                t_after_logic = time.perf_counter()
                logic_ms = int((t_after_logic - t_logic) * 1000)
                print(f"[REPLY] {reply}")
                t_tts = time.perf_counter()
                try:
                    pcm_out, sr = self.client.tts_pcm16(reply)
                except Exception as e:
                    print(f"[API TTS Error] {e}")
                    continue
                t_after_tts_fetch = time.perf_counter()
                tts_first_ms = int((t_after_tts_fetch - t_tts) * 1000)
                self._speak_pcm(pcm_out, sr)
                t_end = time.perf_counter()
                playback_ms = int((t_end - t_after_tts_fetch) * 1000)
                print(
                    "[LATENCY] "
                    f"capture={timings['capture_ms']}ms, "
                    f"stt={timings['stt_ms']}ms, "
                    f"logic={logic_ms}ms, "
                    f"tts_first_byte={tts_first_ms}ms, "
                    f"tts_playback≈{playback_ms}ms"
                )
        except KeyboardInterrupt:
            print("\n[Synq] Stopping...")
        finally:
            self._running = False
