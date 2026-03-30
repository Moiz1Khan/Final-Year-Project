"""Shared web session + JWT file write after login."""

from __future__ import annotations

from fastapi import Request

from synq.auth.auth_token_file import write_auth_token
from synq.auth.jwt_tokens import create_access_token
from synq.auth.session import write_active_session
from synq.auth.users import get_user


def browser_login(request: Request, user_id: int) -> None:
    request.session["user_id"] = user_id
    write_active_session(user_id)
    u = get_user(user_id)
    write_auth_token(create_access_token(user_id=user_id, email=u.email if u else None))
