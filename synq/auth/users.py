"""User accounts (multi-tenant)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from synq.memory.db import get_connection, init_db


@dataclass
class User:
    id: int
    name: str
    email: Optional[str]
    has_password: bool
    google_sub: Optional[str] = None


def claim_default_user(
    *,
    name: str,
    email: Optional[str],
    password: str,
) -> int:
    """If the only user has no password (legacy Default), upgrade that row; else create."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("SELECT id, password_hash FROM users ORDER BY id")
        rows = cur.fetchall()
        if len(rows) == 1 and not (rows[0]["password_hash"] or "").strip():
            uid = int(rows[0]["id"])
            conn.execute(
                "UPDATE users SET name = ?, email = ?, password_hash = ? WHERE id = ?",
                (
                    name.strip() or "User",
                    (email or "").strip() or None,
                    generate_password_hash(password),
                    uid,
                ),
            )
            conn.commit()
            return uid
    finally:
        conn.close()
    return create_user(name=name, email=email, password=password)


def create_user(
    *,
    name: str,
    email: Optional[str],
    password: str,
) -> int:
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name.strip() or "User", (email or "").strip() or None, generate_password_hash(password)),
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    finally:
        conn.close()


def verify_login(*, email_or_name: str, password: str) -> Optional[int]:
    """Return user_id if credentials match."""
    init_db()
    q = (email_or_name or "").strip()
    if not q or not password:
        return None
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, password_hash FROM users
            WHERE (email IS NOT NULL AND LOWER(email) = LOWER(?))
               OR LOWER(name) = LOWER(?)
            """,
            (q, q),
        )
        row = cur.fetchone()
        if not row or not row["password_hash"]:
            return None
        if check_password_hash(row["password_hash"], password):
            return int(row["id"])
        return None
    finally:
        conn.close()


def get_user(user_id: int) -> Optional[User]:
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, name, email, password_hash, google_sub FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        keys = set(row.keys())
        gsub = row["google_sub"] if "google_sub" in keys else None
        return User(
            id=int(row["id"]),
            name=row["name"] or "User",
            email=row["email"],
            has_password=bool(row["password_hash"]),
            google_sub=(gsub.strip() or None) if isinstance(gsub, str) and gsub.strip() else None,
        )
    finally:
        conn.close()


def list_users() -> List[User]:
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, name, email, password_hash, google_sub FROM users ORDER BY id"
        )
        return [
            User(
                id=int(r["id"]),
                name=r["name"] or "User",
                email=r["email"],
                has_password=bool(r["password_hash"]),
                google_sub=(r["google_sub"] or None) if r["google_sub"] else None,
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def user_count() -> int:
    init_db()
    conn = get_connection()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    finally:
        conn.close()


def any_user_with_password() -> bool:
    init_db()
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL AND password_hash != ''"
        ).fetchone()[0]
        return int(n) > 0
    finally:
        conn.close()


def any_login_eligible_user() -> bool:
    """True if at least one user can sign in (password and/or Google OAuth)."""
    init_db()
    conn = get_connection()
    try:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM users WHERE
              (password_hash IS NOT NULL AND TRIM(password_hash) != '')
              OR (google_sub IS NOT NULL AND TRIM(google_sub) != '')
            """
        ).fetchone()[0]
        return int(n) > 0
    finally:
        conn.close()


def upsert_google_account(*, google_sub: str, email: Optional[str], name: str) -> int:
    """
    Create or update user from Google sign-in. Links by google_sub, then email (no sub yet),
    else upgrades sole legacy Default row, else inserts.
    """
    init_db()
    sub = (google_sub or "").strip()
    if not sub:
        raise ValueError("google_sub required")
    em = (email or "").strip() or None
    nm = (name or "").strip() or "User"

    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM users WHERE google_sub = ?", (sub,)).fetchone()
        if row:
            uid = int(row["id"])
            conn.execute(
                "UPDATE users SET email = COALESCE(?, email) WHERE id = ?",
                (em, uid),
            )
            conn.commit()
            return uid

        if em:
            er = conn.execute(
                """
                SELECT id, google_sub FROM users
                WHERE email IS NOT NULL AND LOWER(email) = LOWER(?)
                """,
                (em,),
            ).fetchone()
            if er and not (er["google_sub"] or "").strip():
                uid = int(er["id"])
                conn.execute(
                    "UPDATE users SET google_sub = ?, email = ? WHERE id = ?",
                    (sub, em, uid),
                )
                conn.commit()
                return uid

        rows = list(conn.execute("SELECT id, password_hash, google_sub FROM users").fetchall())
        if len(rows) == 1:
            r = rows[0]
            if not (r["password_hash"] or "").strip() and not (r["google_sub"] or "").strip():
                uid = int(r["id"])
                conn.execute(
                    "UPDATE users SET name = ?, email = ?, google_sub = ? WHERE id = ?",
                    (nm, em, sub, uid),
                )
                conn.commit()
                return uid

        conn.execute(
            "INSERT INTO users (name, email, password_hash, google_sub) VALUES (?, ?, NULL, ?)",
            (nm, em, sub),
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    finally:
        conn.close()


def update_user_display_name(user_id: int, name: str) -> None:
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET name = ? WHERE id = ?",
            ((name or "").strip() or "User", int(user_id)),
        )
        conn.commit()
    finally:
        conn.close()
