"""OpenAI Chat API for NLU - flexible intent + module routing."""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass
class IntentResult:
    intent: str
    response: str
    module: Optional[str]
    entities: Dict[str, str]
    confidence: float


class OpenAINLU:
    """
    LLM-based NLU - understands any phrasing, routes to modules.
    Returns intent, module name, entities, and suggested response.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        agent_name: str = "Synq",
        modules: Optional[List[Dict[str, Any]]] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.agent_name = agent_name
        self.modules = modules or []
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)

    def register_modules(self, modules: List[Dict[str, Any]]):
        """Register available voice-accessible modules."""
        self.modules = modules

    def process(self, text: str, context: Optional[str] = None) -> IntentResult:
        """Parse user command, determine intent and module, generate response."""
        self._ensure_client()
        text = text.strip()
        if not text:
            return IntentResult(
                intent="no_input",
                response="I didn't catch that. Could you repeat?",
                module=None,
                entities={},
                confidence=0.0,
            )

        modules_desc = "\n".join(
            f"- {m['name']}: {m.get('description', '')}" for m in self.modules
        ) if self.modules else "No modules registered."

        context_block = ""
        if context and context.strip():
            context_block = f"\n\nUser context (remember this):\n{context}\n"

        sys_prompt = f"""You are {self.agent_name}, a voice assistant. Parse the user's command and respond.{context_block}

Available modules (route to these when relevant):
{modules_desc}

Respond with a JSON object:
{{
  "intent": "short intent name",
  "module": "module name or null if general",
  "entities": {{"key": "extracted value"}},
  "response": "Natural spoken response - keep it concise for voice"
}}

Handle: greetings, time, help, thanks, goodbye. Route complex requests to the right module.

IMPORTANT: For activity/screen/context questions, ALWAYS set "module": "activity":
- "what was I doing", "what have I been working on", "summarize my activity", "what apps was I using"
These MUST route to the activity module - do not respond yourself, set module: "activity" so the system can fetch real data.

IMPORTANT: For productivity questions, ALWAYS set "module": "productivity":
- tasks: "add a task", "create a task", "what tasks are pending", "complete task 3", "find the task about X"
- reminders: "remind me tomorrow", "set a reminder", "my reminders"
- calendar/meetings: ALWAYS use module "productivity" and intent "schedule_meeting" for: "schedule a meeting", "schedule meeting", "book a call", "create a meeting", "add calendar event", "meeting link", "generate meeting link", "meeting in X minutes", "meeting in five minutes"
- email: "send an email to", "email Sarah", "read my unread emails", "check my email"

Never guess missing critical fields:
- meeting scheduling requires participants + date + time (duration optional)
- sending email requires recipient + content (subject can be generated if missing)
If information is missing, set module to "productivity" and ask ONE short clarifying question in the JSON response.

If unclear, ask for clarification. Be brief - this is voice, not text."""

        try:
            r = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
            )
            content = r.choices[0].message.content
            data = json.loads(content)
            return IntentResult(
                intent=data.get("intent", "unknown"),
                response=data.get("response", "I'm not sure how to help."),
                module=data.get("module"),
                entities=data.get("entities", {}),
                confidence=0.95,
            )
        except Exception as e:
            return IntentResult(
                intent="error",
                response=f"Sorry, I had trouble understanding. Could you try again?",
                module=None,
                entities={},
                confidence=0.0,
            )
