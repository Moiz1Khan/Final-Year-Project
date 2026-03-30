"""
Gmail integration: send email, list unread, fetch message metadata.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

from synq.integrations.google_auth import get_credentials


GMAIL_SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_READ_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _build_service(scopes: List[str]):
    from googleapiclient.discovery import build

    creds = get_credentials(scopes)
    return build("gmail", "v1", credentials=creds)


def send_email(*, to_email: str, subject: str, body: str, cc: Optional[List[str]] = None) -> str:
    """
    Send an email via Gmail. Returns message id.
    """
    service = _build_service(GMAIL_SEND_SCOPES)

    msg = EmailMessage()
    msg["To"] = to_email
    if cc:
        msg["Cc"] = ", ".join([x for x in cc if x])
    msg["Subject"] = subject
    msg.set_content(body)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent.get("id", "")


def list_unread(*, max_results: int = 10) -> List[str]:
    """Return unread message IDs."""
    service = _build_service(GMAIL_READ_SCOPES)
    r = service.users().messages().list(userId="me", q="is:unread", maxResults=max_results).execute()
    msgs = r.get("messages") or []
    return [m.get("id", "") for m in msgs if m.get("id")]


def get_message_metadata(message_id: str) -> Dict[str, Any]:
    """
    Fetch message metadata and snippet.
    Returns: {id, threadId, snippet, headers{From,Subject,Date}}
    """
    service = _build_service(GMAIL_READ_SCOPES)
    m = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="metadata", metadataHeaders=["From", "Subject", "Date"])
        .execute()
    )
    headers = {h["name"]: h.get("value", "") for h in (m.get("payload", {}).get("headers") or [])}
    return {
        "id": m.get("id", ""),
        "threadId": m.get("threadId", ""),
        "snippet": m.get("snippet", "") or "",
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "raw": m,
    }

