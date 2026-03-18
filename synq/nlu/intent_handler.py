"""Intent recognition and response generation for voice commands."""

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from synq.stt.base import TranscriptResult


@dataclass
class IntentResult:
    """Recognized intent and response."""
    intent: str
    response: str
    entities: Dict[str, str]
    confidence: float


class IntentHandler:
    """
    Simple pattern-based intent handler.
    Matches commands to intents and returns responses.
    Extensible for LLM integration later.
    """

    def __init__(self, agent_name: str = "Synq"):
        self.agent_name = agent_name
        self._intent_patterns: List[tuple] = []

    def _strip_wake_word(self, text: str) -> str:
        """Remove wake phrases from start of transcript."""
        text = text.lower().strip()
        wake_variants = [
            r"^(hey\s+synq|hi\s+synq|synq|hey\s+sync|hi\s+sync|sync)\s*[,.]?\s*",
        ]
        for pattern in wake_variants:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text.strip()

    def add_intent(
        self,
        intent: str,
        patterns: List[str],
        response: str,
        response_fn: Optional[Callable[..., str]] = None,
    ) -> None:
        """Add intent with regex patterns."""
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._intent_patterns.append((intent, compiled, response, response_fn))

    def _register_default_intents(self) -> None:
        """Register common voice agent intents."""
        self.add_intent(
            "greeting",
            [r"^(hi|hello|hey|good morning|good evening|howdy)\s*$"],
            f"Hello! I'm {self.agent_name}. How can I help you?",
        )
        self.add_intent(
            "greeting_question",
            [r"^(how are you|how're you|what'?s up|how do you do)\s*$"],
            "I'm doing great, thanks for asking! What can I do for you?",
        )
        self.add_intent(
            "name",
            [r"^(what'?s? your name|who are you|what are you)\s*$"],
            f"I'm {self.agent_name}, your voice assistant. Nice to meet you!",
        )
        self.add_intent(
            "capabilities",
            [r"^(what can you do|help|capabilities|what are your features)\s*$"],
            "I can respond to your voice commands. Try asking me the time, setting a timer, "
            "or say 'what's the weather' once we add those features. For now, say 'hello' or 'what can you do'.",
        )
        self.add_intent(
            "thanks",
            [r"^(thank you|thanks|thank you very much)\s*$"],
            "You're welcome! Anything else?",
        )
        self.add_intent(
            "goodbye",
            [r"^(goodbye|bye|see you|later)\s*$"],
            "Goodbye! I'll be here when you need me.",
        )
        self.add_intent(
            "time",
            [r"^(what('s| is) the time|what time is it|current time)\s*$"],
            "",
            response_fn=lambda m: f"The current time is {__import__('datetime').datetime.now().strftime('%I:%M %p')}.",
        )
        self.add_intent(
            "unknown",
            [],  # Fallback
            "I'm not sure how to help with that yet. Try asking 'what can you do'.",
        )

    def _normalize(self, text: str) -> str:
        """Lowercase, strip, remove trailing punctuation."""
        text = text.lower().strip()
        text = re.sub(r"[?.!,\s]+$", "", text)
        return text.strip()

    def process(self, transcript: TranscriptResult) -> IntentResult:
        """Match transcript to intent and return response."""
        if not self._intent_patterns:
            self._register_default_intents()

        text = self._strip_wake_word(transcript.text)
        text = self._normalize(text)
        if not text:
            return IntentResult(
                intent="no_input",
                response="I didn't catch that. Could you repeat?",
                entities={},
                confidence=0.0,
            )

        for intent, patterns, default_response, response_fn in self._intent_patterns:
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    response = response_fn(match) if response_fn else default_response
                    return IntentResult(
                        intent=intent,
                        response=response,
                        entities=match.groupdict(),
                        confidence=transcript.confidence,
                    )

        return IntentResult(
            intent="unknown",
            response="I'm not sure how to help with that yet. Try asking 'what can you do'.",
            entities={},
            confidence=0.5,
        )
