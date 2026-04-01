"""Helper functions for active window and process detection (Windows)."""

from __future__ import annotations

import sys
from typing import List, Set, Tuple


def get_active_window() -> Tuple[str, str]:
    """
    Get the currently active window's process name and title.
    Returns (process_name, window_title). Returns ("", "") on failure or non-Windows.
    """
    if sys.platform != "win32":
        return ("", "")

    try:
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ("", "")

        title = win32gui.GetWindowText(hwnd)
        if title is None:
            title = ""

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return ("", title)

        import psutil

        proc = psutil.Process(pid)
        process_name = proc.name() or ""
        return (process_name, title)

    except Exception:
        return ("", "")


def get_visible_windows_snapshot(max_items: int = 24) -> List[Tuple[str, str]]:
    """
    Sample of visible top-level windows: (process_name, window_title).
    Used for honest answers about what is open on screen (not LLM guesses).
    """
    if sys.platform != "win32":
        return []

    try:
        import win32gui
        import win32process
        import psutil

        seen: Set[Tuple[str, str]] = set()
        out: List[Tuple[str, str]] = []

        def _enum(hwnd: int, _: object) -> None:
            if len(out) >= max_items * 3:
                return
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd) or ""
                if not title.strip() or title in ("Program Manager", "MSCTFIME UI"):
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if not pid:
                    return
                pname = (psutil.Process(pid).name() or "").lower()
                key = (pname, title[:100])
                if key in seen:
                    return
                seen.add(key)
                out.append((pname, title[:160]))
            except Exception:
                return

        win32gui.EnumWindows(_enum, None)
        return out[:max_items]
    except Exception:
        return []
