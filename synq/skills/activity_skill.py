"""
Activity skill - voice-accessible "What was I doing?" via context monitoring.
Calls get_recent_activity() and get_activity_summary(), uses LLM to generate spoken summary.
"""

import json
import os
from typing import Any, Dict

from synq.context_monitoring import get_activity_summary, get_recent_activity
from synq.skills.base import Skill, SkillResult
from synq.skills.registry import register_skill


class ActivitySkill(Skill):
    name = "activity"
    description = "Summarize recent computer activity - what apps used, what you were doing. User asks 'what was I doing?', 'what have I been working on?', 'summarize my activity'."

    def handle(self, intent: str, entities: Dict[str, Any], raw_text: str) -> SkillResult:
        try:
            recent = get_recent_activity(limit=30)
            summary = get_activity_summary(hours=24)

            if not recent and not summary.get("by_app"):
                return SkillResult(
                    success=True,
                    response="I don't have any activity logged yet. The context monitor may not have been running, or there's no recent data.",
                )

            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                response = self._summarize_with_llm(api_key, recent, summary, raw_text)
            else:
                response = self._summarize_text(recent, summary)

            return SkillResult(success=True, response=response)
        except Exception as e:
            return SkillResult(
                success=False,
                response=f"Sorry, I couldn't fetch your activity. {str(e)}",
            )

    def _summarize_with_llm(
        self,
        api_key: str,
        recent: list,
        summary: dict,
        raw_text: str,
    ) -> str:
        """Use LLM to generate a natural, brief spoken summary."""
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Build compact data for the prompt
        recent_str = json.dumps(recent[:15], indent=0) if recent else "[]"
        by_app = summary.get("by_app", {})
        top_apps = list(by_app.items())[:10]
        summary_str = json.dumps(dict(top_apps), indent=0)

        prompt = f"""You are a voice assistant. The user asked: "{raw_text}"

Here is their recent computer activity data:
- Recent activity (last 15 entries): {recent_str}
- Time spent per app (approx minutes, last 24h): {summary_str}

Generate a SHORT, spoken response (2-4 sentences) summarizing what they've been doing. Be conversational and natural for voice. Focus on the main apps and activities. Do not list raw data or timestamps."""

        try:
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception:
            return self._summarize_text(recent, summary)

    def _summarize_text(self, recent: list, summary: dict) -> str:
        """Fallback: simple text summary without LLM."""
        by_app = summary.get("by_app", {})
        if not by_app and not recent:
            return "No activity data available."

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


register_skill(ActivitySkill())
