"""Helper functions for active window and process detection (Windows)."""

import sys
from typing import Tuple


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
