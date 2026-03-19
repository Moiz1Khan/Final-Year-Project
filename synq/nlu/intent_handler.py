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
            [
                r"^(hi|hello|hey|howdy|hi there|hey there)\s*$",
                r"^(good morning|good afternoon|good evening)\s*$",
            ],
            f"Hello! I'm {self.agent_name}. How can I help you?",
        )
        self.add_intent(
            "greeting_question",
            [
                r"^(how are you|how're you|what'?s up|how do you do|how'?s it going)\s*$",
                r"^(what'?s going on|how are things|how'?s everything)\s*$",
            ],
            "I'm doing great, thanks for asking! What can I do for you?",
        )
        self.add_intent(
            "name",
            [
                r"^(what'?s? your name|who are you|what are you|who is this)\s*$",
                r"^(introduce yourself|tell me about yourself)\s*$",
            ],
            f"I'm {self.agent_name}, your voice assistant. Nice to meet you!",
        )
        self.add_intent(
            "capabilities",
            [
                r"^(what can you do|help|capabilities|what are your features)\s*$",
                r"^(what do you do|how can you help|what do you offer)\s*$",
                r"^(i need help|i need assistance|can you help me)\s*$",
                r"^(what are you capable of|your abilities)\s*$",
            ],
            "I can tell you the time, summarize your recent activity, and more. "
            "Try 'what time is it' or 'what was I doing?'. Ask 'what can you do' for the full list.",
        )
        self.add_intent(
            "thanks",
            [
                r"^(thank you|thanks|thank you very much|thanks a lot|ty)\s*$",
                r"^(appreciate it|i appreciate that|grateful)\s*$",
            ],
            "You're welcome! Anything else?",
        )
        self.add_intent(
            "goodbye",
            [
                r"^(goodbye|bye|see you|later|see you later|bye bye)\s*$",
                r"^(take care|have a good one|talk to you later)\s*$",
            ],
            "Goodbye! I'll be here when you need me.",
        )
        self.add_intent(
            "yes_affirm",
            [
                r"^(yes|yeah|yep|yup|ok|okay|sure|alright|of course|absolutely)\s*$",
                r"^(sounds good|sounds great|that works|got it)\s*$",
            ],
            "Great! What else can I do for you?",
        )
        self.add_intent(
            "no_cancel",
            [
                r"^(no|nope|nah|never mind|nevermind)\s*$",
                r"^(cancel|stop|that'?s it|i'?m done|no thanks)\s*$",
            ],
            "No problem. Let me know if you need anything else.",
        )
        self.add_intent(
            "repeat",
            [
                r"^(what|sorry|pardon|excuse me)\s*$",
                r"^(can you repeat|say that again|what did you say|come again)\s*$",
                r"^(i didn'?t hear|i didn'?t catch that|one more time)\s*$",
            ],
            "I'll say it again. What would you like me to help with?",
        )
        self.add_intent(
            "presence_check",
            [
                r"^(can you hear me|are you there|hello\?|testing|test)\s*$",
                r"^(you there|anybody home|anyone there)\s*$",
            ],
            "Yes, I'm here and listening! How can I help you?",
        )
        self.add_intent(
            "compliment",
            [
                r"^(you'?re great|you'?re helpful|good job|well done|nice job)\s*$",
                r"^(that'?s helpful|that was helpful|thanks that helped)\s*$",
                r"^(nice to meet you|good to meet you|pleasure to meet you)\s*$",
            ],
            "Thank you! Happy to help. Anything else?",
        )
        self.add_intent(
            "small_talk",
            [
                r"^(what'?s new|what'?s new with you|anything new)\s*$",
                r"^(tell me something|say something|entertain me)\s*$",
                r"^(that'?s (cool|interesting|neat)|interesting|cool)\s*$",
            ],
            "Not much new on my end! I'm here whenever you need me. Try asking 'what time is it' or 'what was I doing?'",
        )
        self.add_intent(
            "date",
            [
                r"^(what'?s the date|what date is it|what'?s today'?s date)\s*$",
                r"^(what day is it|what day is today)\s*$",
            ],
            "",
            response_fn=lambda m: f"Today is {__import__('datetime').datetime.now().strftime('%A, %B %d, %Y')}.",
        )
        self.add_intent(
            "time",
            [r"^(what('s| is) the time|what time is it|current time)\s*$"],
            "",
            response_fn=lambda m: f"The current time is {__import__('datetime').datetime.now().strftime('%I:%M %p')}.",
        )
        self.add_intent(
            "activity",
            [
                r"what\s+(was|have|did)\s+i\s+(doing|do)",
                r"summarize\s+my\s+activity",
                r"what\s+(have\s+i\s+)?been\s+working\s+on",
                r"what\s+was\s+i\s+up\s+to",
                r"my\s+(recent\s+)?activity",
                r"(tell\s+me\s+)?(about\s+)?(my\s+)?(recent\s+)?activity",
                r"what\s+(have\s+i\s+)?(been\s+)?(up\s+to|working\s+on)",
            ],
            "",
            response_fn=self._activity_response,
        )
        self.add_intent(
            "unknown",
            [],  # Fallback
            "I'm not sure how to help with that yet. Try asking 'what can you do'.",
        )

    def _activity_response(self, match) -> str:
        """Return activity summary from context monitoring (local mode)."""
        try:
            from synq.context_monitoring import get_activity_summary, get_recent_activity

            recent = get_recent_activity(limit=30)
            summary = get_activity_summary(hours=24)
            by_app = summary.get("by_app", {})
            if not by_app and not recent:
                return "I don't have any activity logged yet. The context monitor may not have been running."
            parts = []
            if by_app:
                top = list(by_app.items())[:5]
                apps = ", ".join(f"{a} ({m} min)" for a, m in top)
                parts.append(f"In the last 24 hours you spent time in: {apps}.")
            if recent:
                latest = recent[0]
                app = latest.get("active_app", "")
                title = (latest.get("window_title", "") or "")[:50]
                status = latest.get("status", "")
                parts.append(f"Most recently you were in {app}." + (f' "{title}"' if title else "") + f" ({status}).")
            return " ".join(parts)
        except ImportError:
            return "Context monitoring is not available. Enable it in config to track your activity."
        except Exception as e:
            return f"Sorry, I couldn't fetch your activity. {e}"

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
