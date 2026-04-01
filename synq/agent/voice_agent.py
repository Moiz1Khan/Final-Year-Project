"""
Synq Voice Agent - FYP-style system with our logic.
Uses PyAudio (record until silence), pygame (playback with interrupt).
Our logic: wake word / face gate, intents, NLU.
"""

import re
import time
from pathlib import Path
from typing import Optional

import pyaudio

from synq.audio.recorder import PyAudioRecorder, get_rms
from synq.gate.face_gate import check_face_gate
from synq.stt.base import SpeechToText, TranscriptResult
from synq.wake_word.whisper_detector import WhisperWakeWordDetector


class VoiceAgent:
    """
    FYP system + Synq logic:
    - Gate: face recognition or wake word
    - Record: PyAudio (until silence)
    - Transcribe: Whisper
    - Process: our NLU
    - Play: pygame with interrupt-on-speech
    """

    def __init__(
        self,
        gate_mode: str,
        wake_detector: Optional[WhisperWakeWordDetector],
        stt: SpeechToText,
        tts,  # SynqTTS or ApiTTS
        recorder: PyAudioRecorder,
        orchestrator,  # Orchestrator
        device_index: Optional[int] = None,
        debug: bool = False,
        active_user_id: int = 1,
    ):
        self.gate_mode = gate_mode
        self.wake_detector = wake_detector
        self.stt = stt
        self.tts = tts
        self.recorder = recorder
        self.orchestrator = orchestrator
        self.device_index = device_index
        self.debug = debug
        self.active_user_id = active_user_id
        self._running = False

    def _strip_wake(self, text: str) -> str:
        text = text.lower().strip()
        for p in [
            r"^(hey\s+synq|hi\s+synq|synq|hey\s+sync|hi\s+sync|sync|hey\s+sink|hi\s+sink|sink)\s*[,.]?\s*",
        ]:
            text = re.sub(p, "", text, flags=re.IGNORECASE)
        return text.strip()

    def _run_gate(self) -> bool:
        """Run gate. Returns True to proceed to record, False to skip."""
        if self.gate_mode == "none":
            return True
        if self.gate_mode == "face":
            return check_face_gate(timeout_seconds=30, show_camera=False)
        return True

    def _wait_for_wake_word(self) -> Optional[str]:
        """Listen for wake word via PyAudio + Whisper. Returns transcript if command in same utterance."""
        if not self.wake_detector:
            return None

        self.wake_detector.start()
        p = pyaudio.PyAudio()
        chunk = self.recorder.chunk
        chunk_bytes = chunk * 2

        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.recorder.sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=chunk,
        )

        chunks_fed = 0
        try:
            print("\n[LISTENING] Say 'Hey Synq'... (or use gate_mode: none to skip)")
            while self._running:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                except OSError:
                    continue
                chunks_fed += 1
                if self.debug and chunks_fed % 50 == 0:
                    print(f"  ... listening ({chunks_fed} chunks)")
                event = self.wake_detector.process_audio_frame(data)
                if event:
                    print("\n[OK] Wake word heard!")
                    self.wake_detector.stop()
                    stream.close()
                    p.terminate()
                    cmd = self._strip_wake(event.full_transcript or event.phrase)
                    if cmd and len(cmd) > 2:
                        return cmd
                    return ""
        except KeyboardInterrupt:
            pass
        finally:
            self.wake_detector.stop()
            try:
                stream.close()
                p.terminate()
            except Exception:
                pass
        return None

    def _record_command(self) -> tuple[Optional[str], Optional[dict]]:
        """Record until silence (in-memory), transcribe, return text + timings."""
        print("[RECORDING] Speak now. Will stop after silence...")
        timings = {
            "capture_ms": 0,
            "stt_ms": 0,
        }
        t_capture_start = time.perf_counter()
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
        try:
            while self._running:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                except OSError:
                    continue
                rms = get_rms(data)
                if rms > silence_threshold:
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
            print("[WARN] No audio recorded (too quiet or no speech)")
            return None, None

        audio_bytes = b"".join(frames)
        timings["capture_ms"] = int((time.perf_counter() - t_capture_start) * 1000)

        if len(audio_bytes) < 2000:
            print("[WARN] Audio too short")
            return None, None

        print("[TRANSCRIBING] Please wait...")
        t_stt_start = time.perf_counter()
        result = self.stt.transcribe(audio_bytes, sample_rate)
        timings["stt_ms"] = int((time.perf_counter() - t_stt_start) * 1000)
        text = result.text.strip() if result else None
        if text:
            print(f"[HEARD] \"{text}\"")
        else:
            print("[WARN] No speech detected")
        return text, timings

    def _process_and_respond(self, text: str) -> bool:
        """Process command, speak response. Returns False if interrupted."""
        if not text:
            print("[REPLY] I didn't catch that.")
            self.tts.speak("I didn't catch that. Could you repeat?")
            return True

        response = self.orchestrator.process(
            TranscriptResult(text=text, confidence=1.0, is_final=True),
            user_id=self.active_user_id,
        )
        print(f"[REPLY] {response}")
        return self.tts.speak(response, interruptible=True)

    def run(self) -> None:
        self._running = True
        print("=" * 50)
        print("Synq Voice Agent")
        print("=" * 50)
        mode = getattr(self.orchestrator, "use_api", False)
        print("Mode:", "API (production)" if mode else "Local")
        print("Gate:", self.gate_mode)
        if self.gate_mode == "face":
            print("Face recognition required before each turn.")
        elif self.gate_mode == "wake_word":
            print("Say 'Hey Synq' to activate.")
        else:
            print("No gate - always listening. Speak anytime!")
        print("Press Ctrl+C to exit\n")
        print(f"Active user id: {self.active_user_id}\n")

        try:
            import time
            while self._running:
                self.tts.stop()
                # Keep a very short handoff gap for audio device stability.
                time.sleep(0.05)

                if self.gate_mode == "face":
                    if not self._run_gate():
                        if self.debug:
                            print("[Gate] Face recognition failed, skipping")
                        continue
                    print("\nFace recognized. Listening for command...")
                elif self.gate_mode == "wake_word":
                    wake_result = self._wait_for_wake_word()
                    if wake_result is None:
                        break
                    if wake_result and len(wake_result) > 2:
                        self._process_and_respond(wake_result)
                        continue
                    print("\n[OK] Yes? Listening for command...")
                else:
                    print("\n[READY] Listening for command...")

                cmd_text, timings = self._record_command()
                if cmd_text:
                    print(f"[Synq] You said: {cmd_text}")
                    t_logic_start = time.perf_counter()
                    interrupted = not self._process_and_respond(cmd_text)
                    t_logic_end = time.perf_counter()
                    if timings is not None:
                        logic_tts_ms = int((t_logic_end - t_logic_start) * 1000)
                        tts_first_byte_ms = 0
                        tts_playback_ms = 0
                        tts_metrics = getattr(self.tts, "last_metrics", None)
                        if isinstance(tts_metrics, dict):
                            tts_first_byte_ms = int(tts_metrics.get("first_byte_ms", 0) or 0)
                            tts_playback_ms = int(tts_metrics.get("playback_ms", 0) or 0)
                        logic_ms = max(0, logic_tts_ms - tts_playback_ms)
                        total_ms = (
                            timings["capture_ms"]
                            + timings["stt_ms"]
                            + logic_ms
                            + tts_playback_ms
                        )
                        print(
                            "[LATENCY] "
                            f"capture={timings['capture_ms']}ms, "
                            f"stt={timings['stt_ms']}ms, "
                            f"logic={logic_ms}ms, "
                            f"tts_first_byte={tts_first_byte_ms}ms, "
                            f"tts_playback={tts_playback_ms}ms, "
                            f"total={total_ms}ms"
                        )
                    if interrupted:
                        print("\nInterrupted. Ready for next command.")

        except KeyboardInterrupt:
            print("\n\n[Synq] Stopping...")
        finally:
            self._running = False
            try:
                from synq.context_monitoring import stop_monitor

                stop_monitor()
            except ImportError:
                pass
            try:
                from synq.email_monitoring.monitor import stop_email_monitor

                stop_email_monitor()
            except ImportError:
                pass

    def stop(self) -> None:
        self._running = False


def create_agent_from_config(
    config_path: Optional[Path] = None,
    debug_override: Optional[bool] = None,
) -> VoiceAgent:
    """Build agent from config. Supports api, local, and realtime modes."""
    import os
    import yaml
    from dotenv import load_dotenv

    from synq.auth.context import set_active_user_id
    from synq.auth.session import apply_user_env, resolve_active_user_id
    from synq.memory.db import get_connection, init_db

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv()
    init_db()
    resolved = resolve_active_user_id()
    if resolved is not None:
        active_user_id = resolved
    else:
        conn = get_connection()
        try:
            row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        finally:
            conn.close()
        active_user_id = int(row[0]) if row else 1
    set_active_user_id(active_user_id)

    cfg_path = config_path or project_root / "config" / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    audio_cfg = cfg.get("audio", {})
    device_index = audio_cfg.get("device")
    debug = debug_override if debug_override is not None else cfg.get("debug", False)
    voice_backend = (cfg.get("voice") or {}).get("backend", "local")

    if voice_backend == "synq_cloud":
        from synq.agent.remote_voice_agent import RemoteVoiceAgent
        from synq.auth.auth_token_file import read_auth_token
        from synq.services.synq_cloud_client import SynqCloudClient

        token = read_auth_token()
        if not token:
            raise RuntimeError(
                "voice.backend is 'synq_cloud' but no JWT found. "
                "Sign in via the web console (http://127.0.0.1:8765) to create data/auth_token.json, "
                "or call POST /api/auth/login and save the access_token."
            )
        base = (cfg.get("synq_cloud") or {}).get("base_url", "http://127.0.0.1:8765")
        base = str(base).strip().rstrip("/")
        client = SynqCloudClient(base_url=base, access_token=token)
        sample_rate = audio_cfg.get("sample_rate", 16000)
        recorder = PyAudioRecorder(
            sample_rate=sample_rate,
            chunk=1024,
            silence_threshold=audio_cfg.get("silence_threshold", 1000),
            silence_duration=audio_cfg.get("silence_duration", 0.9),
            device_index=device_index,
            max_wait_speech_seconds=float(audio_cfg.get("max_wait_speech_seconds", 25)),
            max_record_seconds=float(audio_cfg.get("max_record_seconds", 120)),
        )
        return RemoteVoiceAgent(
            client=client,
            recorder=recorder,
            device_index=device_index,
            debug=debug,
            active_user_id=active_user_id,
            interrupt_threshold=audio_cfg.get("interrupt_threshold", 50000),
            interrupt_chunks=audio_cfg.get("interrupt_chunks", 3),
        )

    apply_user_env(active_user_id)

    mode = cfg.get("mode", "local")
    api_key = os.getenv("OPENAI_API_KEY")
    use_api = mode in {"api", "realtime"} and bool(api_key)
    if mode in {"api", "realtime"} and not api_key:
        print(f"[WARN] mode={mode} but OPENAI_API_KEY not set. Falling back to local.")
        use_api = False

    api_cfg = cfg.get("api", {}).get("openai", {})
    stt_provider = str(cfg.get("api", {}).get("stt_provider", "elevenlabs")).lower()
    whisper_cfg = cfg.get("whisper", {})
    wk = cfg.get("wake_word", {})
    sample_rate = audio_cfg.get("sample_rate", 16000)
    gate_mode = cfg.get("gate", {}).get("mode", "none")
    agent_name = cfg.get("agent", {}).get("name", "Synq")

    recorder = PyAudioRecorder(
        sample_rate=sample_rate,
        chunk=1024,
        silence_threshold=audio_cfg.get("silence_threshold", 1000),
        silence_duration=audio_cfg.get("silence_duration", 0.9),
        device_index=device_index,
        max_wait_speech_seconds=float(audio_cfg.get("max_wait_speech_seconds", 25)),
        max_record_seconds=float(audio_cfg.get("max_record_seconds", 120)),
    )

    if use_api:
        from synq.orchestrator import Orchestrator

        eleven_key = os.getenv("ELEVENLABS_API_KEY")
        if stt_provider == "elevenlabs" and eleven_key:
            try:
                from synq.services.elevenlabs_stt import ElevenLabsSTT

                stt = ElevenLabsSTT(
                    api_key=eleven_key,
                    model_id=cfg.get("tts", {}).get("elevenlabs", {}).get("stt_model_id", "scribe_v2"),
                )
            except Exception as e:
                print(f"[WARN] ElevenLabs STT unavailable ({e}). Falling back to OpenAI STT.")
                from synq.services.openai_stt import OpenAIWhisperSTT

                stt = OpenAIWhisperSTT(api_key=api_key, model=api_cfg.get("stt_model", "whisper-1"))
        else:
            from synq.services.openai_stt import OpenAIWhisperSTT

            stt = OpenAIWhisperSTT(api_key=api_key, model=api_cfg.get("stt_model", "whisper-1"))

        tts_engine = cfg.get("tts", {}).get("engine", "elevenlabs")
        if tts_engine == "elevenlabs" and eleven_key:
            from synq.services.elevenlabs_tts import ElevenLabsTTS
            tts_cfg = cfg.get("tts", {}).get("elevenlabs", {})
            env_voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
            tts = ElevenLabsTTS(
                api_key=eleven_key,
                voice_id=env_voice or tts_cfg.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
                model_id=tts_cfg.get("model_id", "eleven_flash_v2_5"),
                optimize_streaming_latency=tts_cfg.get("optimize_streaming_latency", 4),
                interrupt_threshold=audio_cfg.get("interrupt_threshold", 50000),
                interrupt_chunks=audio_cfg.get("interrupt_chunks", 3),
            )
        else:
            from synq.tts.api_tts import ApiTTS
            tts = ApiTTS(
                api_key=api_key,
                model=api_cfg.get("tts_model", "tts-1"),
                voice=api_cfg.get("tts_voice", "alloy"),
                interrupt_threshold=audio_cfg.get("interrupt_threshold", 50000),
                interrupt_chunks=audio_cfg.get("interrupt_chunks", 3),
            )

        orchestrator = Orchestrator(
            agent_name=agent_name,
            use_api=True,
            api_key=api_key,
            use_memory=cfg.get("memory", {}).get("enabled", True),
        )
    else:
        from synq.stt.whisper_stt import WhisperSpeechToText
        from synq.tts.synq_tts import SynqTTS
        from synq.orchestrator import Orchestrator

        stt = WhisperSpeechToText(
            model_size=whisper_cfg.get("model_size", "base"),
            device=whisper_cfg.get("device", "cpu"),
            compute_type=whisper_cfg.get("compute_type", "int8"),
            sample_rate=sample_rate,
        )
        tts = SynqTTS(
            interrupt_threshold=audio_cfg.get("interrupt_threshold", 50000),
            interrupt_chunks=audio_cfg.get("interrupt_chunks", 3),
        )
        orchestrator = Orchestrator(agent_name=agent_name, use_api=False)

    wake_detector = None
    if gate_mode == "wake_word":
        phrases = wk.get("phrases", ["hey synq", "hi synq", "synq", "hey sync", "hi sync", "sync"])
        wake_detector = WhisperWakeWordDetector(
            phrases,
            model_size=whisper_cfg.get("model_size", "tiny"),
            sample_rate=sample_rate,
            device=whisper_cfg.get("device", "cpu"),
            compute_type=whisper_cfg.get("compute_type", "int8"),
            debug=debug,
        )

    # Start context monitoring if enabled (background thread)
    cm_cfg = cfg.get("context_monitoring", {})
    if cm_cfg.get("enabled", False):
        try:
            from synq.context_monitoring import start_monitor

            sd = cm_cfg.get("sensitive_data") or {}
            start_monitor(
                poll_interval_seconds=cm_cfg.get("poll_interval_seconds", 5),
                idle_threshold_seconds=cm_cfg.get("idle_threshold_seconds", 60),
                log_interval_seconds=cm_cfg.get("log_interval_seconds", 10),
                truncate_window_title=sd.get("truncate_window_title", 0),
                exclude_apps=sd.get("exclude_apps") or [],
                verbose=debug,
            )
        except ImportError as e:
            if debug:
                print(f"[WARN] Context monitoring not available: {e}")

    # Start email monitoring if enabled (background thread)
    em_cfg = cfg.get("email_monitoring", {})
    if use_api and em_cfg.get("enabled", False):
        try:
            from synq.email_monitoring.monitor import start_email_monitor

            speak_notifications = bool(em_cfg.get("speak_notifications", False))
            log_notifications = bool(em_cfg.get("log_notifications", False))

            def _notify(msg: str) -> None:
                if log_notifications:
                    print(f"[Email] {msg}")
                if speak_notifications:
                    try:
                        # Optional voice notification (disabled by default).
                        tts.speak(msg, interruptible=False)
                    except Exception:
                        pass

            start_email_monitor(
                user_id=active_user_id,
                poll_seconds=int(em_cfg.get("poll_seconds", 30)),
                notify_fn=_notify,
                openai_api_key=api_key,
            )
        except Exception as e:
            if debug:
                print(f"[WARN] Email monitoring not available: {e}")

    # Realtime architecture path (preserves existing logic via Orchestrator)
    if mode == "realtime" and use_api:
        from synq.agent.realtime_voice_agent import RealtimeConfig, RealtimeVoiceAgent

        rt_cfg = cfg.get("realtime", {})
        return RealtimeVoiceAgent(
            stt=stt,
            orchestrator=orchestrator,
            tts=tts,
            active_user_id=active_user_id,
            config=RealtimeConfig(
                sample_rate=sample_rate,
                chunk_ms=int(rt_cfg.get("chunk_ms", 40)),
                endpoint_silence_ms=int(rt_cfg.get("endpoint_silence_ms", 350)),
                min_utterance_ms=int(rt_cfg.get("min_utterance_ms", 250)),
                vad_threshold=float(rt_cfg.get("vad_threshold", 900)),
                execute_on_final_only=bool(rt_cfg.get("execute_on_final_only", True)),
            ),
            device_index=device_index,
            debug=debug,
        )

    return VoiceAgent(
        gate_mode=gate_mode,
        wake_detector=wake_detector,
        stt=stt,
        tts=tts,
        recorder=recorder,
        orchestrator=orchestrator,
        device_index=device_index,
        debug=debug,
        active_user_id=active_user_id,
    )
