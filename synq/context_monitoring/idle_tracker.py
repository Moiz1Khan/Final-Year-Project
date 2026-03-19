"""Idle time detection using Windows GetLastInputInfo (ctypes, no extra deps)."""

import ctypes
import sys
from typing import Optional


def get_idle_seconds() -> float:
    """
    Return seconds since last keyboard/mouse input.
    Uses GetLastInputInfo on Windows. Returns 0.0 on non-Windows.
    """
    if sys.platform != "win32":
        return 0.0

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        user32.GetLastInputInfo(ctypes.byref(lii))

        millis = kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0

    except Exception:
        return 0.0


def is_idle(threshold_seconds: float) -> bool:
    """
    Return True if user has been idle (no keyboard/mouse) for at least
    threshold_seconds.
    """
    return get_idle_seconds() >= threshold_seconds
