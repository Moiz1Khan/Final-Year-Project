"""
Productivity skill - executive assistant actions via voice.

Handles:
- Tasks/reminders (stored in SQLite; indexed in Chroma for semantic search)
- Calendar scheduling (Google Calendar)
- Email send/read/notify (Gmail)

This module is designed to be routed by OpenAINLU as module="productivity".
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from synq.skills.base import Skill, SkillResult
from synq.skills.registry import register_skill

from synq.auth.context import get_active_user_id
from synq.productivity.storage import add_reminder, add_task, complete_task, list_reminders, list_tasks
from synq.productivity.vector_store import ProductivityVectorStore, task_doc


class ProductivitySkill(Skill):
    name = "productivity"
    description = (
        "Task management, reminders, calendar scheduling, and email. "
        "Examples: 'add a task to submit my report Friday', 'what tasks are pending', "
        "'find the task about presentation', 'remind me tomorrow at 9am to call Ali', "
        "'schedule a meeting with Ali tomorrow at 5pm', "
        "'send an email to Sarah about the report', 'read my unread emails'."
    )

    def handle(self, intent: str, entities: Dict[str, Any], raw_text: str) -> SkillResult:
        # NOTE: This module will be extended further (Google APIs + follow-ups).
        # For now, tasks/reminders + semantic search are implemented locally.
        t = (raw_text or "").strip()
        t_l = t.lower()

        uid = entities.get("user_id")
        user_id = int(uid) if uid is not None else get_active_user_id()

        # --- create task ---
        if intent in {"create_task", "add_task"} or "add task" in t_l or t_l.startswith("task:"):
            title = (entities.get("title") or "").strip()
            if not title:
                # crude extraction: "add task <title>"
                m = re.search(r"(add\s+task|task:)\s*(.+)$", t, re.IGNORECASE)
                title = (m.group(2) if m else "").strip()
            if not title:
                return SkillResult(success=True, response="What should the task be called?")

            notes = (entities.get("notes") or "").strip()
            priority = (entities.get("priority") or "normal").strip().lower()
            due_at = (entities.get("due_at") or "").strip() or None
            task_id = add_task(user_id, title=title, notes=notes, priority=priority, due_at=due_at)

            vs = ProductivityVectorStore(api_key=os.getenv("OPENAI_API_KEY"), collection_name="synq_tasks")
            vs.upsert(
                doc_id=f"t_{user_id}_{task_id}",
                user_id=user_id,
                document=task_doc(title=title, notes=notes, due_at=due_at or "", status="pending", priority=priority),
                metadata={"type": "task", "task_id": task_id, "status": "pending"},
            )

            return SkillResult(success=True, response=f"Done. I added task {task_id}: {title}.")

        # --- list tasks ---
        if intent in {"list_tasks"} or "what tasks" in t_l or "pending tasks" in t_l or t_l.startswith("list tasks"):
            tasks = list_tasks(user_id, status="pending", limit=10)
            if not tasks:
                return SkillResult(success=True, response="You have no pending tasks.")
            items = "; ".join(f"{x.id}. {x.title}" for x in tasks[:6])
            return SkillResult(success=True, response=f"Here are your pending tasks: {items}.")

        # --- complete task ---
        if intent in {"complete_task", "finish_task"} or t_l.startswith("complete task"):
            tid = entities.get("task_id")
            if tid is None:
                m = re.search(r"complete\s+task\s+(\d+)", t_l)
                tid = int(m.group(1)) if m else None
            if tid is None:
                return SkillResult(success=True, response="Which task number should I mark complete?")
            ok = complete_task(user_id, int(tid))
            return SkillResult(success=True, response=("Done." if ok else "I couldn't find that task."))

        # --- semantic search tasks ---
        if intent in {"search_tasks", "find_task"} or t_l.startswith("find task") or "find the task" in t_l:
            q = (entities.get("query") or "").strip()
            if not q:
                m = re.search(r"find\s+(the\s+)?task\s+(about\s+)?(.+)$", t, re.IGNORECASE)
                q = (m.group(3) if m else "").strip()
            if not q:
                return SkillResult(success=True, response="What should I search your tasks for?")
            vs = ProductivityVectorStore(api_key=os.getenv("OPENAI_API_KEY"), collection_name="synq_tasks")
            hits = vs.query(user_id=user_id, query_text=q, top_k=3)
            if not hits:
                return SkillResult(success=True, response="I couldn't find a matching task.")
            # Voice-friendly: read top hit title line.
            first = hits[0].splitlines()[0].replace("Task:", "").strip()
            return SkillResult(success=True, response=f"The closest match is: {first}.")

        # --- set reminder (stored; scheduling/notifications added later) ---
        if intent in {"set_reminder", "create_reminder"} or "remind me" in t_l:
            title = (entities.get("title") or "").strip()
            due_at = (entities.get("due_at") or "").strip()
            if not title:
                title = t
            if not due_at:
                return SkillResult(success=True, response="When should I remind you?")
            rid = add_reminder(user_id, title=title, due_at=due_at, metadata={"raw_text": t})
            return SkillResult(success=True, response=f"Okay. Reminder {rid} set for {due_at}.")

        if intent in {"list_reminders"} or "my reminders" in t_l:
            rems = list_reminders(user_id, include_notified=False, limit=5)
            if not rems:
                return SkillResult(success=True, response="You have no upcoming reminders.")
            items = "; ".join(f"{r.id}. {r.title} at {r.due_at}" for r in rems)
            return SkillResult(success=True, response=f"Your reminders: {items}.")

        # --- schedule meeting (Google Calendar + Meet link) ---
        if (
            intent in {"schedule_meeting", "create_meeting", "book_meeting"}
            or "schedule a meeting" in t_l
            or "schedule meeting" in t_l
            or "book a call" in t_l
            or "meeting link" in t_l
            or "generate" in t_l and "meeting" in t_l
            or "meeting in" in t_l
        ):
            return self._handle_schedule_meeting(entities, t, t_l, user_id)

        # --- read / check email (Gmail) ---
        if (
            intent in {"read_email", "check_email", "list_emails"}
            or "read my email" in t_l
            or "read my emails" in t_l
            or "check my email" in t_l
            or "unread emails" in t_l
            or "any new email" in t_l
            or "recent email" in t_l
            or "latest email" in t_l
            or "most recent email" in t_l
        ):
            return self._handle_read_email(t_l)

        # --- send email (Gmail) ---
        if (
            intent in {"send_email", "email_send"}
            or "send an email" in t_l
            or "send email" in t_l
            or "email " in t_l and (" to " in t_l or " sarah" in t_l or " john" in t_l)
        ):
            return self._handle_send_email(entities, t, t_l)

        return SkillResult(
            success=True,
            response=(
                "I can manage tasks, reminders, calendar, and email. "
                "Try 'add task buy milk' or 'what tasks are pending'."
            ),
        )

    def _parse_relative_minutes(self, text: str) -> Optional[int]:
        """Parse 'in N minutes' or 'in N hours' from text. Returns total minutes from now."""
        t_l = text.lower()
        # "in 5 minutes", "in five minutes", "in 1 hour"
        word_numbers = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        m = re.search(r"in\s+(\d+)\s*minutes?", t_l)
        if m:
            return int(m.group(1))
        m = re.search(r"in\s+(one|two|three|four|five|six|seven|eight|nine|ten)\s*minutes?", t_l)
        if m:
            return word_numbers.get(m.group(1), 0)
        m = re.search(r"in\s+(\d+)\s*hours?", t_l)
        if m:
            return int(m.group(1)) * 60
        m = re.search(r"in\s+(one|two|three|four|five)\s*hours?", t_l)
        if m:
            return word_numbers.get(m.group(1), 0) * 60
        return None

    def _handle_schedule_meeting(
        self, entities: Dict[str, Any], raw_text: str, raw_lower: str, user_id: int
    ) -> SkillResult:
        title = (entities.get("title") or entities.get("summary") or "").strip() or "Meeting"
        participants = entities.get("participants") or entities.get("attendees")
        if isinstance(participants, str):
            participants = [e.strip() for e in participants.split(",") if e.strip()]
        elif not isinstance(participants, list):
            participants = []
        # Parse start time: from entities or from "in N minutes" in raw text
        start_iso = (entities.get("start_iso") or entities.get("time") or entities.get("date") or "").strip()
        minutes_from_now = self._parse_relative_minutes(raw_text)
        if minutes_from_now is not None:
            start_dt = datetime.utcnow() + timedelta(minutes=minutes_from_now)
            start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        if not start_iso:
            return SkillResult(
                success=True,
                response="When should the meeting be? Say for example 'in 5 minutes' or 'tomorrow at 5pm'.",
            )
        try:
            from synq.integrations.google_calendar import create_meeting_event
        except ImportError as e:
            return SkillResult(
                success=False,
                response="Calendar is not set up. Add Google OAuth credentials and try again.",
            )
        try:
            event = create_meeting_event(
                summary=title,
                start_iso=start_iso,
                end_iso=None,
                attendees_emails=participants if participants else None,
                description="",
                timezone="UTC",
            )
            meet_link = ""
            if isinstance(event, dict):
                entry = (event.get("conferenceData") or {}).get("entryPoints") or []
                for ep in entry:
                    if ep.get("entryPointType") == "video":
                        meet_link = ep.get("uri") or ""
                        break
                if not meet_link and event.get("hangoutLink"):
                    meet_link = event.get("hangoutLink", "")
            if meet_link:
                return SkillResult(
                    success=True,
                    response=f"Done. Meeting scheduled. Here's your Meet link: {meet_link}",
                )
            return SkillResult(success=True, response="Meeting created on your calendar.")
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            return SkillResult(
                success=False,
                response=f"I couldn't create the meeting. {err}",
            )

    def _handle_read_email(self, query_text: str = "") -> SkillResult:
        """List unread emails and return a short voice summary."""
        try:
            from synq.integrations.gmail_client import get_message_metadata, list_unread
        except ImportError:
            return SkillResult(
                success=False,
                response="Gmail is not set up. Add Google OAuth credentials and try again.",
            )
        try:
            ids = list_unread(max_results=5)
            if not ids:
                return SkillResult(success=True, response="You have no unread emails.")
            wants_latest = any(
                p in (query_text or "")
                for p in ["most recent", "latest", "last one", "recent one", "most recent email"]
            )
            if wants_latest:
                meta = get_message_metadata(ids[0])
                sender = (meta.get("from") or "Unknown sender").strip()
                subj = (meta.get("subject") or "(no subject)").strip()
                return SkillResult(
                    success=True,
                    response=f"Your most recent unread email is from {sender}. Subject: {subj}.",
                )
            parts = []
            for mid in ids[:3]:
                meta = get_message_metadata(mid)
                sender = (meta.get("from") or "").strip()[:40]
                subj = (meta.get("subject") or "(no subject)").strip()[:50]
                parts.append(f"From {sender}: {subj}")
            summary = "; ".join(parts)
            if len(ids) > 3:
                summary += f". You have {len(ids)} unread in total."
            return SkillResult(success=True, response=summary)
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            return SkillResult(success=False, response=f"I couldn't fetch your emails. {err}")

    def _handle_send_email(
        self, entities: Dict[str, Any], raw_text: str, raw_lower: str
    ) -> SkillResult:
        """Send email via Gmail. Asks for recipient/body if missing."""
        to_email = (entities.get("recipient") or entities.get("to") or "").strip()
        if not to_email:
            # Try "email Sarah" or "send email to john"
            m = re.search(r"(?:send\s+)?(?:an?\s+)?email\s+to\s+(\S+(?:\s+\S+)?)", raw_lower)
            if m:
                to_email = m.group(1).strip()
            if not to_email:
                return SkillResult(
                    success=True,
                    response="Who should I send the email to? Say the person's name or address.",
                )
        # Normalize: "sarah" -> assume sarah@gmail.com or ask? We'll use as-is if it contains @
        if "@" not in to_email:
            to_email = to_email.replace(" ", "") + "@gmail.com"  # best-effort
        subject = (entities.get("subject") or "").strip()
        if not subject:
            subject = "Message from Synq"
        body = (entities.get("body") or entities.get("content") or "").strip()
        if not body:
            body = "Sent by voice via Synq."
        try:
            from synq.integrations.gmail_client import send_email
        except ImportError:
            return SkillResult(
                success=False,
                response="Gmail is not set up. Add Google OAuth credentials and try again.",
            )
        try:
            send_email(to_email=to_email, subject=subject, body=body)
            return SkillResult(
                success=True,
                response=f"Done. Email sent to {to_email}.",
            )
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            return SkillResult(success=False, response=f"I couldn't send the email. {err}")


register_skill(ProductivitySkill())

