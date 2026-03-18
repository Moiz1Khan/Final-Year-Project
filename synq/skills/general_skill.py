"""General skill - greetings, help, etc. Fallback when no specific module."""

from synq.skills.base import Skill, SkillResult
from synq.skills.registry import get_registry, register_skill


class GeneralSkill(Skill):
    name = "general"
    description = "Greetings, help, thanks, goodbye"

    def handle(self, intent: str, entities: dict, raw_text: str) -> SkillResult:
        registry = get_registry()
        modules = [m["name"] for m in registry.list_for_nlu()]
        if intent == "capabilities" or "help" in raw_text.lower():
            mods = ", ".join(m for m in modules if m != "general") or "time"
            return SkillResult(
                success=True,
                response=f"I can help with: {mods}. Say 'what time is it' or 'help' for more. More modules coming soon!",
            )
        return SkillResult(success=False, response="")


register_skill(GeneralSkill())
