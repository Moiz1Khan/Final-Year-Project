"""
SQLite storage for productivity module:
- tasks
- reminders
- email cache (seen messages)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from synq.memory.db import get_connection, init_db


@dataclass
class Task:
    id: int
    title: str
    notes: str
    priority: str
    status: str
    due_at: Optional[str]


@dataclass
class Reminder:
    id: int
    title: str
    due_at: str
    notified: int


def add_task(
    user_id: int,
    *,
    title: str,
    notes: str = "",
    priority: str = "normal",
    due_at: Optional[str] = None,
) -> int:
    init_db(None)
    conn = get_connection(None)
    try:
        conn.execute(
            """
            INSERT INTO tasks (user_id, title, notes, priority, due_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, title, notes or "", priority or "normal", due_at),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def list_tasks(user_id: int, *, status: str = "pending", limit: int = 20) -> List[Task]:
    init_db(None)
    conn = get_connection(None)
    try:
        cur = conn.execute(
            """
            SELECT id, title, notes, priority, status, due_at
            FROM tasks
            WHERE user_id = ? AND status = ?
            ORDER BY
              CASE WHEN due_at IS NULL OR due_at = '' THEN 1 ELSE 0 END,
              due_at ASC,
              created_at DESC
            LIMIT ?
            """,
            (user_id, status, limit),
        )
        return [
            Task(
                id=r["id"],
                title=r["title"],
                notes=r["notes"] or "",
                priority=r["priority"] or "normal",
                status=r["status"],
                due_at=r["due_at"],
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def complete_task(user_id: int, task_id: int) -> bool:
    init_db(None)
    conn = get_connection(None)
    try:
        cur = conn.execute(
            """
            UPDATE tasks
            SET status='done', completed_at=datetime('now')
            WHERE user_id = ? AND id = ? AND status != 'done'
            """,
            (user_id, task_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_reminder(user_id: int, *, title: str, due_at: str, metadata: Optional[Dict[str, Any]] = None) -> int:
    init_db(None)
    conn = get_connection(None)
    try:
        conn.execute(
            """
            INSERT INTO reminders (user_id, title, due_at, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title, due_at, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def list_reminders(user_id: int, *, include_notified: bool = False, limit: int = 20) -> List[Reminder]:
    init_db(None)
    conn = get_connection(None)
    try:
        if include_notified:
            where = ""
            args = (user_id, limit)
        else:
            where = "AND notified = 0"
            args = (user_id, limit)
        cur = conn.execute(
            f"""
            SELECT id, title, due_at, notified
            FROM reminders
            WHERE user_id = ? {where}
            ORDER BY due_at ASC
            LIMIT ?
            """,
            args,
        )
        return [
            Reminder(
                id=r["id"],
                title=r["title"],
                due_at=r["due_at"],
                notified=int(r["notified"] or 0),
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def mark_reminder_notified(user_id: int, reminder_id: int) -> None:
    init_db(None)
    conn = get_connection(None)
    try:
        conn.execute(
            "UPDATE reminders SET notified = 1 WHERE user_id = ? AND id = ?",
            (user_id, reminder_id),
        )
        conn.commit()
    finally:
        conn.close()


def cache_email(
    user_id: int,
    *,
    message_id: str,
    thread_id: str = "",
    from_email: str = "",
    subject: str = "",
    snippet: str = "",
    received_at: str = "",
    raw_json: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if inserted; False if already existed."""
    init_db(None)
    conn = get_connection(None)
    try:
        try:
            conn.execute(
                """
                INSERT INTO email_cache
                  (user_id, message_id, thread_id, from_email, subject, snippet, received_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    message_id,
                    thread_id or "",
                    from_email or "",
                    subject or "",
                    snippet or "",
                    received_at or "",
                    json.dumps(raw_json or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return True
        except Exception:
            return False
    finally:
        conn.close()

