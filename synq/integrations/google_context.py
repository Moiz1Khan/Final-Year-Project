"""Per-request Google OAuth user (API server concurrency-safe)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Generator, Optional

_google_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "synq_google_user_id", default=None
)


def get_google_user_id() -> Optional[int]:
    return _google_user_id.get()


@contextmanager
def google_user_context(user_id: int) -> Generator[None, None, None]:
    token = _google_user_id.set(user_id)
    try:
        yield
    finally:
        _google_user_id.reset(token)
