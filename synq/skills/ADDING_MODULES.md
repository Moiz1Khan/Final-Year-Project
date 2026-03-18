# Adding Voice-Accessible Modules

Every module you add becomes voice-accessible. Users can say things like "set a timer" or "what's the weather" and Synq routes to the right module.

## 1. Create a skill file

Create `synq/skills/my_module_skill.py`:

```python
from synq.skills.base import Skill, SkillResult
from synq.skills.registry import register_skill


class MyModuleSkill(Skill):
    name = "my_module"
    description = "What your module does - user says X to trigger"

    def handle(self, intent: str, entities: dict, raw_text: str) -> SkillResult:
        # entities may contain: {"duration": "5 minutes", "action": "set"}
        # Do your logic, call APIs, control devices, etc.
        return SkillResult(
            success=True,
            response="Done! I've started the timer for 5 minutes.",
        )


register_skill(MyModuleSkill())
```

## 2. Register in orchestrator

In `synq/orchestrator.py`, add to the import:

```python
from synq.skills import time_skill, general_skill, my_module_skill
```

## 3. That's it

The LLM (OpenAI) will see your module in the list and route commands to it. No hardcoded patterns – it understands natural phrasing.
