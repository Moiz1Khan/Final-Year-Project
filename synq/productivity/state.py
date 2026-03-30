"""
Pending action state for multi-turn follow-ups.

We store a single most-recent pending action per user in SQLite so the assistant
can ask a missing-field question and complete it on the next utterance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from synq.memory.db import get_connection, init_db


@dataclass
class PendingAction:
    id: int
    user_id: int
    action: Dict[str, Any]


def get_pending_action(user_id: int) -> Optional[PendingAction]:
    init_db(None)
    conn = get_connection(None)
    try:
        cur = conn.execute(
            """
            SELECT id, user_id, action_json
            FROM pending_actions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            action = json.loads(row["action_json"])
        except Exception:
            action = {"raw": row["action_json"]}
        return PendingAction(id=row["id"], user_id=row["user_id"], action=action)
    finally:
        conn.close()


def set_pending_action(user_id: int, action: Dict[str, Any]) -> int:
    init_db(None)
    conn = get_connection(None)
    try:
        conn.execute(
            "INSERT INTO pending_actions (user_id, action_json) VALUES (?, ?)",
            (user_id, json.dumps(action, ensure_ascii=False)),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def clear_pending_actions(user_id: int) -> None:
    init_db(None)
    conn = get_connection(None)
    try:
        conn.execute("DELETE FROM pending_actions WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()

