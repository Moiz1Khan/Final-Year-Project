"""
Background Gmail monitor (polling).

Polls unread emails and emits notifications via a callback.
Persists seen message IDs into SQLite email_cache to avoid duplicates.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from synq.productivity.storage import cache_email
from synq.productivity.vector_store import ProductivityVectorStore, email_doc
from synq.integrations.gmail_client import get_message_metadata, list_unread


NotifyFn = Callable[[str], None]

_thread: Optional[threading.Thread] = None
_running = False


def start_email_monitor(
    *,
    user_id: int = 1,
    poll_seconds: int = 30,
    notify_fn: Optional[NotifyFn] = None,
    openai_api_key: Optional[str] = None,
) -> None:
    global _thread, _running
    if _thread and _thread.is_alive():
        return

    _running = True
    notify = notify_fn or (lambda msg: print(f"[Email] {msg}"))
    vs = ProductivityVectorStore(api_key=openai_api_key, collection_name="synq_emails")

    def loop():
        global _running
        while _running:
            try:
                ids = list_unread(max_results=10)
                for mid in ids:
                    meta = get_message_metadata(mid)
                    inserted = cache_email(
                        user_id,
                        message_id=meta.get("id", ""),
                        thread_id=meta.get("threadId", ""),
                        from_email=meta.get("from", ""),
                        subject=meta.get("subject", ""),
                        snippet=meta.get("snippet", ""),
                        received_at=meta.get("date", ""),
                        raw_json=meta.get("raw", {}),
                    )
                    if not inserted:
                        continue

                    # index for semantic search
                    vs.upsert(
                        doc_id=f"e_{user_id}_{meta.get('id','')}",
                        user_id=user_id,
                        document=email_doc(meta.get("from", ""), meta.get("subject", ""), meta.get("snippet", "")),
                        metadata={"type": "email", "message_id": meta.get("id", "")},
                    )

                    sender = meta.get("from", "") or "Unknown sender"
                    subject = meta.get("subject", "") or "(no subject)"
                    notify(f"New email from {sender}. Subject: {subject}.")
            except Exception as e:
                notify(f"Email monitor error: {e}")

            for _ in range(max(1, poll_seconds)):
                if not _running:
                    break
                time.sleep(1)

    _thread = threading.Thread(target=loop, daemon=True)
    _thread.start()


def stop_email_monitor() -> None:
    global _running, _thread
    _running = False
    _thread = None

