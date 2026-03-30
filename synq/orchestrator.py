"""
Orchestrator - processes voice commands with full memory.
API mode: OpenAINLU + SkillRegistry + MemoryStore
Local mode: IntentHandler (pattern-based)
"""

from typing import Optional
import threading

from synq.stt.base import TranscriptResult


class Orchestrator:
    """Unified command processor with memory."""

    def __init__(
        self,
        agent_name: str = "Synq",
        use_api: bool = True,
        api_key: Optional[str] = None,
        use_memory: bool = True,
    ):
        self.agent_name = agent_name
        self.use_api = use_api
        self.api_key = api_key
        self.use_memory = use_memory and bool(api_key)
        self._nlu = None
        self._handler = None
        self._registry = None
        self._memory = None

    def _persist_turn_async(self, user_id: int, text: str, response: str) -> None:
        """
        Persist conversation/memory in background to reduce turn latency.
        This keeps user-visible behavior the same while moving non-critical work off the hot path.
        """
        if not self._memory:
            return

        def _worker() -> None:
            try:
                self._memory.save_turn(user_id, "user", text)
                self._memory.save_turn(user_id, "assistant", response)
                from synq.memory.extractor import extract_memories
                for mem_type, mem_content in extract_memories(text, response, self.api_key):
                    self._memory.add_memory(user_id, mem_type, mem_content)
            except Exception:
                # Background persistence should not impact voice turn.
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _ensure_loaded(self):
        if self.use_api and self.api_key:
            if self._nlu is None:
                from synq.services.openai_nlu import OpenAINLU
                from synq.skills.registry import get_registry
                from synq.skills import time_skill, general_skill, activity_skill, productivity_skill
                self._registry = get_registry()
                self._nlu = OpenAINLU(api_key=self.api_key, agent_name=self.agent_name)
                self._nlu.register_modules(self._registry.list_for_nlu())
            if self.use_memory and self._memory is None:
                from synq.memory.store import MemoryStore
                self._memory = MemoryStore(api_key=self.api_key)
        else:
            if self._handler is None:
                from synq.nlu.intent_handler import IntentHandler
                self._handler = IntentHandler(self.agent_name)

    def process(
        self,
        transcript: TranscriptResult,
        user_id: Optional[int] = None,
    ) -> str:
        """Process command, return response. Uses memory when enabled."""
        self._ensure_loaded()
        text = transcript.text.strip()
        if not text:
            return "I didn't catch that. Could you repeat?"

        user_id = self._memory.ensure_user(user_id) if self._memory else 1

        context = ""
        if self._memory:
            from synq.memory.context import build_context
            context = build_context(self._memory, user_id, text)

        if self.use_api and self._nlu:
            result = self._nlu.process(text, context=context)
            response = result.response
            if result.module and self._registry:
                skill_result = self._registry.execute(
                    result.module, result.intent, result.entities, text
                )
                if skill_result and skill_result.success and skill_result.response:
                    response = skill_result.response

            if self._memory:
                self._persist_turn_async(user_id, text, response)

            return response

        r = self._handler.process(transcript)
        return r.response
