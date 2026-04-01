"""Desktop skill - safe local desktop automations."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from synq.desktop.actions import execute_action, normalize_app_name
from synq.skills.base import Skill, SkillResult
from synq.skills.registry import register_skill

DESKTOP_SKILL_FALLBACK_REPLY = (
    "I can automate desktop actions like opening apps, searching the web, "
    "keyboard shortcuts, media controls, and routines."
)


class DesktopSkill(Skill):
    name = "desktop"
    description = (
        "Desktop automation: open apps/sites, web search, open folders/files, type text, "
        "keypress shortcuts, media controls, and routines. "
        "Examples: 'open chrome', 'search web for python logging', "
        "'open folder Downloads', 'press control s', 'run morning routine'."
    )

    def handle(self, intent: str, entities: Dict[str, Any], raw_text: str) -> SkillResult:
        t = (raw_text or "").strip()
        tl = t.lower()
        action = (entities.get("action") or "").strip().lower()
        if action:
            return self._execute(action, entities)

        if re.search(r"\b(create|make|add)\s+(a\s+|the\s+|my\s+)?(new\s+)?python\s+file\b", tl):
            fn_m = re.search(r"\b(?:named|called)\s+([\w\-.]+\.py)\b", t, re.IGNORECASE)
            fn = fn_m.group(1) if fn_m else ""
            return self._execute("vscode_new_file", {"filename": fn})

        yt = self._try_youtube(t, tl)
        if yt is not None:
            return yt

        if tl.startswith("open app "):
            return self._open_app_with_optional_followup(
                self._clean_app_target(t[9:].strip()), tl
            )
        if tl.startswith("open "):
            target = t[5:].strip()
            if target.startswith(("http://", "https://")) or self._looks_like_url_target(target):
                return self._execute("open_url", {"url": target})
            return self._open_app_with_optional_followup(self._clean_app_target(target), tl)
        m = re.search(r"\bopen\s+(.+)$", t, flags=re.IGNORECASE)
        if m:
            target = self._clean_app_target(m.group(1).strip())
            if target:
                return self._open_app_with_optional_followup(target, tl)
        if tl.startswith(("go to ", "open website ")):
            s = re.sub(r"^(go to|open website)\s+", "", t, flags=re.IGNORECASE).strip()
            return self._execute("open_url", {"url": s})
        if tl.startswith(("search ", "search web for ", "google ")):
            q = re.sub(r"^(search web for|search|google)\s+", "", t, flags=re.IGNORECASE).strip()
            return self._execute("search_web", {"query": q})
        if tl.startswith(("open folder ", "open file ", "open path ")):
            p = re.sub(r"^(open folder|open file|open path)\s+", "", t, flags=re.IGNORECASE).strip()
            return self._execute("open_path", {"path": p})
        if tl.startswith("type "):
            return self._execute("type_text", {"text": t[5:]})
        if tl.startswith("copy this "):
            return self._execute("clipboard_set", {"text": t[10:]})
        if tl.startswith(("press ", "shortcut ")):
            return self._execute("key_press", {"keys": self._parse_keys(t)})
        if "switch window" in tl:
            direction = "prev" if ("previous" in tl or "back" in tl) else "next"
            return self._execute("window_switch", {"direction": direction})
        if "play pause" in tl or "pause music" in tl or "resume music" in tl:
            return self._execute("media_key", {"name": "play_pause"})
        if "next track" in tl or "skip song" in tl:
            return self._execute("media_key", {"name": "next"})
        if "previous track" in tl:
            return self._execute("media_key", {"name": "prev"})
        if "mute" in tl and "unmute" not in tl:
            return self._execute("media_key", {"name": "mute_toggle"})
        if "volume up" in tl:
            return self._execute("media_key", {"name": "volume_up"})
        if "volume down" in tl:
            return self._execute("media_key", {"name": "volume_down"})
        if tl.startswith(("run routine ", "start routine ")):
            name = re.sub(r"^(run routine|start routine)\s+", "", t, flags=re.IGNORECASE).strip()
            return self._execute("run_routine", {"name": name})

        return SkillResult(success=True, response=DESKTOP_SKILL_FALLBACK_REPLY)

    def _try_youtube(self, t: str, tl: str) -> Optional[SkillResult]:
        if "youtube" not in tl:
            return None
        play = any(k in tl for k in ("play", "song", "music", "video"))
        url = (
            "https://www.youtube.com/results?search_query=music"
            if play
            else "https://www.youtube.com/"
        )
        r = execute_action("open_chrome_url", {"url": url})
        if not r.ok:
            return SkillResult(success=False, response=r.message)
        extra = (
            " Note: I can't auto-play a specific YouTube video from here - "
            "focus Chrome and click a result or press Space."
        )
        return SkillResult(success=True, response=r.message + extra)

    def _open_app_with_optional_followup(self, app: str, tl: str) -> SkillResult:
        r = execute_action("open_app", {"app": app})
        if not r.ok:
            return SkillResult(success=False, response=r.message)
        if normalize_app_name(app) == "spotify" and ("play" in tl or "song" in tl):
            execute_action("wait_ms", {"ms": 1500})
            m = execute_action("media_key", {"name": "play_pause"})
            return SkillResult(
                success=m.ok,
                response=(
                    f"{r.message} I also sent a media play/pause key; Spotify may start or resume playback."
                ),
            )
        return SkillResult(success=True, response=r.message)

    def _parse_keys(self, text: str) -> List[str]:
        raw = re.sub(r"^(press|shortcut)\s+", "", text, flags=re.IGNORECASE).strip().lower()
        raw = raw.replace("control", "ctrl").replace(" plus ", "+").replace(" and ", "+")
        parts = [p.strip() for p in raw.split("+") if p.strip()]
        return parts or [raw]

    def _looks_like_url_target(self, target: str) -> bool:
        s = (target or "").strip()
        if not s:
            return False
        if s.startswith(("http://", "https://")):
            return True
        return bool(re.search(r"\b[A-Za-z0-9][A-Za-z0-9\-]*\.[A-Za-z]{2,}\b", s))

    def _strip_compound_trailing(self, phrase: str) -> str:
        x = (phrase or "").strip()
        x = re.sub(r"\s+on\s+chrome\s+and\s+.*$", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\s+and\s+(play|start|open)\s+.*$", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\s+then\s+(play|open).*$", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\s+and\s+(a\s+)?(song|music).*$", "", x, flags=re.IGNORECASE)
        return x.strip()

    def _clean_app_target(self, target: str) -> str:
        x = self._strip_compound_trailing((target or "").strip())
        x = re.sub(r"\b(for me|please|on my desktop|on desktop|the app|application)\b", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\b(open|launch|tab)\b", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\b(a|an|the)\b", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\s+", " ", x).strip(" .,!?")
        x = re.sub(r"\s+and\s+(play|a song|music).*$", "", x, flags=re.IGNORECASE)
        x = re.sub(r"\s+", " ", x).strip(" .,!?")
        lx = x.lower()
        if "chrome" in lx:
            return "chrome"
        if "spotify" in lx:
            return "spotify"
        if "vs code" in lx or "v s code" in lx or "visual studio code" in lx or "vscode" in lx:
            return "code"
        if "notepad" in lx:
            return "notepad"
        if "explorer" in lx or "file manager" in lx or "file explorer" in lx:
            return "explorer"
        # Common spoken forms
        if x.lower() in {"vs code", "visual studio code", "v s code"}:
            return "code"
        return x

    def _execute(self, action: str, params: Dict[str, Any]) -> SkillResult:
        r = execute_action(action, params)
        return SkillResult(success=r.ok, response=r.message)


register_skill(DesktopSkill())

