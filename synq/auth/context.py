"""Request/session-scoped active user for skills that need user_id."""

from __future__ import annotations

import contextvars
from typing import Optional

_active_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "synq_active_user_id", default=None
)


def set_active_user_id(user_id: Optional[int]) -> None:
    _active_user_id.set(user_id)


def get_active_user_id() -> int:
    v = _active_user_id.get()
    return int(v) if v is not None else 1
