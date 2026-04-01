"""Client-side factual snapshot for voice (avoids LLM guessing about screen state)."""

from __future__ import annotations

from synq.context_monitoring import get_recent_activity
from synq.context_monitoring.utils import get_active_window, get_visible_windows_snapshot


def looks_like_desktop_fact_question(text: str) -> bool:
    tl = (text or "").lower()
    hints = (
        "what am i",
        "what have i",
        "what's open",
        "whats open",
        "what is open",
        "what tabs",
        "on my screen",
        "right now",
        "past ",
        "minutes",
        "what have i opened",
        "what is opened",
        "analyz",
        "currently",
        "screen",
        "my desktop",
        "windows open",
    )
    return any(h in tl for h in hints)


def build_voice_context_injection() -> str:
    proc, title = get_active_window()
    wins = get_visible_windows_snapshot(22)
    recent = get_recent_activity(limit=14)
    lines = [
        "[FACTS FROM THIS PC - base your answer only on this; do not invent apps, files, or tabs.]",
        f"Foreground (focused) window: process={proc!r}, title={title!r}",
        "Sample of other visible windows (may omit minimized or background apps):",
    ]
    for p, ttl in wins[:20]:
        lines.append(f"  - {p}: {ttl[:100]}")
    if recent:
        lines.append("Recent activity rows (newest first, may overlap foreground):")
        for row in recent[:10]:
            app = row.get("active_app") or ""
            w = (row.get("window_title") or "")[:70]
            st = row.get("status") or ""
            lines.append(f"  - {app} | {w} ({st})")
    return "\n".join(lines)
