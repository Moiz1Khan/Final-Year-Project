"""Base class for voice-accessible skills."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class SkillResult:
    """Result from a skill execution."""
    success: bool
    response: str
    data: Dict[str, Any] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class Skill(ABC):
    """
    Base for voice-accessible modules.
    Register with SkillRegistry to make it voice-accessible.
    """

    name: str
    description: str

    @abstractmethod
    def handle(self, intent: str, entities: Dict[str, Any], raw_text: str) -> SkillResult:
        """Handle the command. entities come from NLU extraction."""
        ...
