"""
Synq Voice Agent - FYP-style system with our logic.
Uses PyAudio (record until silence), pygame (playback with interrupt).
Our logic: wake word / face gate, intents, NLU.
"""

import re
import wave
from pathlib import Path
from typing import Optional

import pyaudio

from synq.audio.recorder import PyAudioRecorder
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
    ):
        self.gate_mode = gate_mode
        self.wake_detector = wake_detector
        self.stt = stt
        self.tts = tts
        self.recorder = recorder
        self.orchestrator = orchestrator
        self.device_index = device_index
        self.debug = debug
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

    def _record_command(self) -> Optional[str]:
        """Record until silence, transcribe, return text."""
        print("[RECORDING] Speak now. Will stop after silence...")
        path = self.recorder.record_to_file(prompt="")
        if path is None:
            print("[WARN] No audio recorded (too quiet or no speech)")
            return None

        try:
            with wave.open(str(path), "rb") as wf:
                audio_bytes = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
        except Exception as e:
            print(f"[ERROR] Read WAV: {e}")
            return None
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        if len(audio_bytes) < 2000:
            print("[WARN] Audio too short")
            return None

        print("[TRANSCRIBING] Please wait...")
        result = self.stt.transcribe(audio_bytes, sample_rate)
        text = result.text.strip() if result else None
        if text:
            print(f"[HEARD] \"{text}\"")
        else:
            print("[WARN] No speech detected")
        return text

    def _process_and_respond(self, text: str) -> bool:
        """Process command, speak response. Returns False if interrupted."""
        if not text:
            print("[REPLY] I didn't catch that.")
            self.tts.speak("I didn't catch that. Could you repeat?")
            return True

        response = self.orchestrator.process(
            TranscriptResult(text=text, confidence=1.0, is_final=True)
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

        try:
            while self._running:
                self.tts.stop()

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

                cmd_text = self._record_command()
                if cmd_text:
                    print(f"[Synq] You said: {cmd_text}")
                    interrupted = not self._process_and_respond(cmd_text)
                    if interrupted:
                        print("\nInterrupted. Ready for next command.")

        except KeyboardInterrupt:
            print("\n\n[Synq] Stopping...")
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False


def create_agent_from_config(
    config_path: Optional[Path] = None,
    debug_override: Optional[bool] = None,
) -> VoiceAgent:
    """Build VoiceAgent from config. Supports api (production) and local modes."""
    import os
    import yaml
    from dotenv import load_dotenv

    load_dotenv()
    project_root = Path(__file__).resolve().parents[2]
    cfg_path = config_path or project_root / "config" / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    mode = cfg.get("mode", "local")
    api_key = os.getenv("OPENAI_API_KEY")
    use_api = mode == "api" and bool(api_key)
    if mode == "api" and not api_key:
        print("[WARN] mode=api but OPENAI_API_KEY not set. Falling back to local.")
        use_api = False

    audio_cfg = cfg.get("audio", {})
    api_cfg = cfg.get("api", {}).get("openai", {})
    whisper_cfg = cfg.get("whisper", {})
    wk = cfg.get("wake_word", {})
    sample_rate = audio_cfg.get("sample_rate", 16000)
    device_index = audio_cfg.get("device")
    debug = debug_override if debug_override is not None else cfg.get("debug", False)
    gate_mode = cfg.get("gate", {}).get("mode", "none")
    agent_name = cfg.get("agent", {}).get("name", "Synq")

    recorder = PyAudioRecorder(
        sample_rate=sample_rate,
        chunk=1024,
        silence_threshold=audio_cfg.get("silence_threshold", 1000),
        silence_duration=audio_cfg.get("silence_duration", 0.9),
        device_index=device_index,
    )

    if use_api:
        from synq.services.openai_stt import OpenAIWhisperSTT
        from synq.orchestrator import Orchestrator

        stt = OpenAIWhisperSTT(api_key=api_key, model=api_cfg.get("stt_model", "whisper-1"))

        tts_engine = cfg.get("tts", {}).get("engine", "elevenlabs")
        eleven_key = os.getenv("ELEVENLABS_API_KEY")
        if tts_engine == "elevenlabs" and eleven_key:
            from synq.services.elevenlabs_tts import ElevenLabsTTS
            tts_cfg = cfg.get("tts", {}).get("elevenlabs", {})
            tts = ElevenLabsTTS(
                api_key=eleven_key,
                voice_id=tts_cfg.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
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

    return VoiceAgent(
        gate_mode=gate_mode,
        wake_detector=wake_detector,
        stt=stt,
        tts=tts,
        recorder=recorder,
        orchestrator=orchestrator,
        device_index=device_index,
        debug=debug,
    )
