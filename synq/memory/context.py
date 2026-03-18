"""Context builder - assembles prompt from memory for each turn."""

from typing import List, Optional, Tuple


def build_context(
    memory_store,
    user_id: int,
    current_message: str,
    recent_limit: int = 20,
    memory_top_k: int = 5,
) -> str:
    """
    Build context string: recent history + relevant memories + upcoming.
    Inject this into the LLM system prompt.
    """
    parts = []

    recent = memory_store.get_recent(user_id, limit=recent_limit)
    if recent:
        lines = []
        for role, content in recent:
            role_label = "User" if role == "user" else "Assistant"
            lines.append(f"{role_label}: {content}")
        parts.append("Recent conversation:\n" + "\n".join(lines[-20:]))

    memories = memory_store.get_relevant_memories(user_id, current_message, top_k=memory_top_k)
    if memories:
        parts.append("Relevant memories:\n" + "\n".join(f"- {m}" for m in memories))

    upcoming = memory_store.get_upcoming_scheduled(user_id, hours_ahead=48)
    if upcoming:
        lines = [f"- {u['title']} (due: {u['due_at']})" for u in upcoming]
        parts.append("Upcoming scheduled:\n" + "\n".join(lines))

    if not parts:
        return ""

    return "\n\n".join(parts) + "\n\n"
