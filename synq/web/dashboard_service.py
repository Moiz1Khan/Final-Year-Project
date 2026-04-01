"""
Dashboard data: DB stats + Google (Gmail/Calendar) under google_user_context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from synq.integrations.google_context import google_user_context
from synq.memory.db import get_connection, init_db
from synq.productivity.storage import list_tasks

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DESKTOP_LOG = _PROJECT_ROOT / "data" / "desktop_actions.log"


@dataclass
class DashboardInsights:
    voice_turns_7d: int = 0
    voice_turns_prev_7d: int = 0
    open_tasks: int = 0
    tasks_due_week: int = 0
    inbox_unread: Optional[int] = None
    mail_recent_7d: Optional[int] = None
    meetings_window: Optional[int] = None
    google_error: Optional[str] = None
    summary_headline: str = "Your Synq overview"
    summary_detail: str = "Connect Google on the Account page to load mail and calendar insights."
    donut_css: str = ""
    donut_pct_calendar: int = 25
    donut_pct_email: int = 25
    donut_pct_voice: int = 25
    donut_pct_other: int = 25
    momentum_pct: int = 35
    table_rows: List[Dict[str, Any]] = field(default_factory=list)


def _count_user_messages_days(user_id: int, days: int) -> int:
    init_db(None)
    conn = get_connection(None)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM conversations
            WHERE user_id = ? AND role = 'user'
              AND datetime(created_at) >= datetime('now', ?)
            """,
            (user_id, f"-{int(days)} days"),
        ).fetchone()
        return int(row["c"] if row else 0)
    finally:
        conn.close()


def _count_tasks_due_this_week(user_id: int) -> int:
    init_db(None)
    conn = get_connection(None)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM tasks
            WHERE user_id = ? AND status = 'pending'
              AND due_at IS NOT NULL AND trim(due_at) != ''
              AND datetime(due_at) <= datetime('now', '+7 days')
              AND datetime(due_at) >= datetime('now', 'start of day')
            """,
            (user_id,),
        ).fetchone()
        return int(row["c"] if row else 0)
    finally:
        conn.close()


def _parse_event_start(ev: Dict[str, Any]) -> Optional[datetime]:
    s = ev.get("start") or {}
    raw = (s.get("dateTime") or s.get("date") or "").strip()
    if not raw:
        return None
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw + "T00:00:00").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_row_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%b %d · %I:%M %p").replace(" 0", " ")


def _event_row(ev: Dict[str, Any], now: datetime, dt: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    dt = dt if dt is not None else _parse_event_start(ev)
    if dt is None:
        return None
    summary = (ev.get("summary") or "Event").strip()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now_u = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if dt < now_u:
        status, pill = "Done", "done"
    else:
        status, pill = "Upcoming", "ok"
    return {
        "kind": "meet",
        "title": summary,
        "when": _format_row_time(dt),
        "when_sort": dt.timestamp(),
        "status": status,
        "pill": pill,
    }


def _mail_row(meta: Dict[str, Any]) -> Dict[str, Any]:
    subj = (meta.get("subject") or "(no subject)").strip()
    sender = (meta.get("from") or "").strip()
    title = subj if len(subj) < 60 else subj[:57] + "…"
    return {
        "kind": "mail",
        "title": title,
        "when": (meta.get("date") or "")[:32] or "—",
        "when_sort": 0.0,
        "status": "Unread",
        "pill": "mail",
        "extra": sender[:48] if sender else "",
    }


def _conic_donut_css(pcts: Tuple[int, int, int, int], colors: Tuple[str, str, str, str]) -> str:
    acc = 0.0
    parts: List[str] = []
    for p, c in zip(pcts, colors):
        start = acc * 3.6
        acc += p
        end = acc * 3.6
        parts.append(f"{c} {start:.1f}deg {end:.1f}deg")
    return f"conic-gradient({', '.join(parts)})"


def _google_ready(user_id: int) -> bool:
    from synq.auth.credentials_store import load_user_secrets

    sec = load_user_secrets(user_id)
    if not sec:
        return False
    return bool((sec.google_token_json or "").strip())


def build_dashboard_insights(user_id: int) -> DashboardInsights:
    out = DashboardInsights()
    out.voice_turns_7d = _count_user_messages_days(user_id, 7)
    out.voice_turns_prev_7d = _count_user_messages_days_range(user_id, 14, 7)
    pending = list_tasks(user_id, status="pending", limit=200)
    out.open_tasks = len(pending)
    out.tasks_due_week = _count_tasks_due_this_week(user_id)

    now = datetime.now(timezone.utc)
    t_min = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    t_max = (now + timedelta(days=21)).isoformat().replace("+00:00", "Z")

    rows: List[Dict[str, Any]] = []

    if _google_ready(user_id):
        try:
            with google_user_context(user_id):
                from synq.integrations import gmail_client
                from synq.integrations.google_calendar import list_events_in_range

                out.inbox_unread = gmail_client.get_inbox_unread_count()
                out.mail_recent_7d = gmail_client.count_messages_newer_than_days(7)

                events = list_events_in_range(time_min_rfc3339=t_min, time_max_rfc3339=t_max, max_results=40)
                out.meetings_window = len(events)
                for ev in events:
                    dt_ev = _parse_event_start(ev)
                    r = _event_row(ev, now, dt_ev)
                    if r:
                        r["when_sort"] = dt_ev.timestamp() if dt_ev else 0
                        rows.append(r)

                try:
                    unread_ids = gmail_client.list_unread(max_results=6)
                    for mid in unread_ids:
                        if not mid:
                            continue
                        meta = gmail_client.get_message_metadata(mid)
                        mr = _mail_row(meta)
                        mr["when_sort"] = now.timestamp()
                        rows.append(mr)
                except Exception:
                    pass

        except Exception as e:
            out.google_error = str(e)[:120]
            out.summary_detail = "Google data could not be loaded. Reconnect on the Account page."

    rows.sort(key=lambda x: -x.get("when_sort", 0))
    out.table_rows = rows[:12]

    # Donut weights
    cal_w = max(out.meetings_window or 0, 1) if out.meetings_window is not None else 1
    mail_w = max((out.inbox_unread or 0) + (out.mail_recent_7d or 0) // 20, 1) if out.mail_recent_7d is not None else 1
    voice_w = max(out.voice_turns_7d, 1)
    other_w = max(out.open_tasks * 2 + 1, 1)
    raw = [cal_w, mail_w, voice_w, other_w]
    tot = sum(raw)
    if tot <= 0:
        p_cal = p_mail = p_voice = p_other = 25
    else:
        p_cal = max(5, int(100 * cal_w / tot))
        p_mail = max(5, int(100 * mail_w / tot))
        p_voice = max(5, int(100 * voice_w / tot))
        p_other = 100 - p_cal - p_mail - p_voice
        if p_other < 5:
            p_other = 5
            p_voice = max(5, p_voice - 5)
    out.donut_pct_calendar = p_cal
    out.donut_pct_email = p_mail
    out.donut_pct_voice = p_voice
    out.donut_pct_other = p_other
    out.donut_css = _conic_donut_css(
        (p_cal, p_mail, p_voice, p_other),
        ("#008b8b", "#2dd4bf", "#67e8f9", "#cbd5e1"),
    )

    # Summary copy
    if out.google_error:
        out.summary_headline = "Partial data"
    elif out.inbox_unread is not None:
        out.summary_headline = "You are synced"
        parts = [
            f"{out.inbox_unread} unread in inbox",
            f"{out.mail_recent_7d or 0} messages touched in the last 7 days",
            f"{out.meetings_window or 0} calendar events in the window",
            f"{out.voice_turns_7d} voice messages this week",
            f"{out.open_tasks} open tasks",
        ]
        out.summary_detail = ". ".join(parts) + "."
    else:
        out.summary_headline = "Welcome"
        out.summary_detail = (
            f"{out.voice_turns_7d} voice messages this week and {out.open_tasks} open tasks. "
            "Connect Google under Account to see mail and meetings here."
        )

    # Momentum bar: voice activity vs soft target
    target = 20
    out.momentum_pct = min(100, int(100 * out.voice_turns_7d / target)) if target else 35

    return out


def _count_user_messages_days_range(user_id: int, days_start: int, days_end: int) -> int:
    """Count user messages where created_at is between now-days_start and now-days_end."""
    init_db(None)
    conn = get_connection(None)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM conversations
            WHERE user_id = ? AND role = 'user'
              AND datetime(created_at) < datetime('now', ?)
              AND datetime(created_at) >= datetime('now', ?)
            """,
            (user_id, f"-{int(days_end)} days", f"-{int(days_start)} days"),
        ).fetchone()
        return int(row["c"] if row else 0)
    finally:
        conn.close()


def voice_delta_percent(current: int, previous: int) -> str:
    if previous <= 0:
        return "+100%" if current > 0 else "0%"
    delta = int(round(100 * (current - previous) / previous))
    return f"+{delta}%" if delta >= 0 else f"{delta}%"


def recent_conversation_feed(user_id: int, limit: int = 40) -> List[Dict[str, str]]:
    init_db(None)
    conn = get_connection(None)
    try:
        cur = conn.execute(
            """
            SELECT role, content, created_at FROM conversations
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [
            {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def desktop_action_lines(limit: int = 40) -> List[str]:
    if not _DESKTOP_LOG.is_file():
        return []
    try:
        raw = _DESKTOP_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    lines = [ln.strip() for ln in raw if ln.strip()]
    return lines[-limit:][::-1]


def filter_activity_lines(lines: List[str], q: str) -> List[str]:
    q = (q or "").strip().lower()
    if not q:
        return lines
    return [ln for ln in lines if q in ln.lower()]
