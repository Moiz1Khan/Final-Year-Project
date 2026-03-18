"""Skill registry - all voice-accessible modules."""

from typing import Any, Callable, Dict, List, Optional

from synq.skills.base import Skill, SkillResult


class SkillRegistry:
    """Central registry of voice-accessible skills."""

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill (module)."""
        self._skills[skill.name] = skill

    def register_handler(
        self,
        name: str,
        description: str,
        handler: Callable[[str, Dict, str], SkillResult],
    ) -> None:
        """Register a handler function as a skill."""
        class Wrapper(Skill):
            pass
        w = type("SkillWrapper", (Skill,), {
            "name": name,
            "description": description,
            "handle": lambda self, i, e, r: handler(i, e, r),
        })()
        self._skills[name] = w

    def get(self, name: str) -> Optional[Skill]:
        """Get skill by name."""
        return self._skills.get(name)

    def list_for_nlu(self) -> List[Dict[str, Any]]:
        """Return module list for NLU routing."""
        return [
            {"name": s.name, "description": s.description}
            for s in self._skills.values()
        ]

    def execute(
        self,
        module_name: str,
        intent: str,
        entities: Dict[str, Any],
        raw_text: str,
    ) -> Optional[SkillResult]:
        """Execute a skill. Returns None if module not found."""
        skill = self._skills.get(module_name)
        if skill is None:
            return None
        return skill.handle(intent, entities, raw_text)


_registry = SkillRegistry()


def register_skill(skill: Skill) -> None:
    _registry.register(skill)


def get_registry() -> SkillRegistry:
    return _registry
