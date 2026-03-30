"""
OpenAI Realtime session wrapper.

This module provides a thin abstraction around realtime transport and keeps
the rest of the app decoupled from websocket details.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class RealtimeEvent:
    type: str
    payload: Dict[str, Any]


class OpenAIRealtimeSession:
    """
    Minimal OpenAI Realtime websocket session manager.

    Notes:
    - If realtime websocket is unavailable, callers can gracefully fall back.
    - Event schema can evolve; unknown events are still forwarded as-is.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        model: str = "gpt-4o-realtime-preview",
        voice: str = "alloy",
        sample_rate: int = 16000,
        debug: bool = False,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.voice = voice
        self.sample_rate = sample_rate
        self.debug = debug
        self._ws = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        self._events: "queue.Queue[RealtimeEvent]" = queue.Queue()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if self._connected:
            return
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is missing for realtime mode.")
        try:
            import websocket  # websocket-client
        except ImportError as e:
            raise RuntimeError("websocket-client is required for realtime mode.") from e

        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1",
        ]
        self._ws = websocket.create_connection(url, header=headers, timeout=10)
        self._connected = True
        self._running = True
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        # Best-effort session settings. Keep text-only + external tool execution in app logic.
        self.send_event(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "voice": self.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                },
            }
        )

    def close(self) -> None:
        self._running = False
        self._connected = False
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    def _listen_loop(self) -> None:
        while self._running and self._ws is not None:
            try:
                raw = self._ws.recv()
                if not raw:
                    continue
                evt = json.loads(raw)
                et = str(evt.get("type", "unknown"))
                self._events.put(RealtimeEvent(type=et, payload=evt))
            except Exception as e:
                if self.debug:
                    print(f"[Realtime] listen error: {e}")
                self._events.put(RealtimeEvent(type="error", payload={"error": str(e)}))
                self._running = False
                self._connected = False
                break

    def send_event(self, event: Dict[str, Any]) -> None:
        if not self._connected or self._ws is None:
            return
        self._ws.send(json.dumps(event))

    def append_input_audio(self, pcm16_chunk: bytes) -> None:
        if not self._connected:
            return
        b64 = base64.b64encode(pcm16_chunk).decode("utf-8")
        self.send_event(
            {
                "type": "input_audio_buffer.append",
                "audio": b64,
            }
        )

    def commit_audio_and_request_response(self) -> None:
        if not self._connected:
            return
        self.send_event({"type": "input_audio_buffer.commit"})
        self.send_event({"type": "response.create"})

    def poll_event(self, timeout_s: float = 0.02) -> Optional[RealtimeEvent]:
        try:
            return self._events.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def cancel_response(self) -> None:
        if not self._connected:
            return
        self.send_event({"type": "response.cancel"})

    def drain_events(self, max_items: int = 500) -> None:
        for _ in range(max_items):
            try:
                self._events.get_nowait()
            except queue.Empty:
                return

