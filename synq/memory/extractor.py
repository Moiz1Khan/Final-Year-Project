"""Extract memories from conversation turn - facts, preferences, events."""

import json
from typing import List, Optional, Tuple

from openai import OpenAI


def extract_memories(
    user_message: str,
    assistant_response: str,
    api_key: str,
    model: str = "gpt-4o-mini",
) -> List[Tuple[str, str]]:
    """
    Extract memories to store. Returns [(memory_type, content), ...].
    memory_type: fact | preference | event
    """
    client = OpenAI(api_key=api_key)

    prompt = f"""From this exchange, extract any NEW facts, preferences, or events worth remembering long-term.
User: {user_message}
Assistant: {assistant_response}

If nothing worth remembering, return empty array.
Return JSON: {{"memories": [{{"type": "fact|preference|event", "content": "..."}}]}}"""

    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(r.choices[0].message.content)
        items = data.get("memories", [])
        return [
            (m.get("type", "fact"), m.get("content", ""))
            for m in items
            if m.get("content") and len(m.get("content", "")) > 10
        ]
    except Exception:
        return []
