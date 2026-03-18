"""Time skill - voice accessible."""

from datetime import datetime
from synq.skills.base import Skill, SkillResult
from synq.skills.registry import register_skill


class TimeSkill(Skill):
    name = "time"
    description = "Current time, date"

    def handle(self, intent: str, entities: dict, raw_text: str) -> SkillResult:
        now = datetime.now()
        return SkillResult(
            success=True,
            response=f"The current time is {now.strftime('%I:%M %p')}. Today is {now.strftime('%A, %B %d')}.",
        )


register_skill(TimeSkill())
