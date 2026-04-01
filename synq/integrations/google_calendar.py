"""
Google Calendar integration (create events with Google Meet link).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from synq.integrations.google_auth import get_credentials


CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def create_meeting_event(
    *,
    summary: str,
    start_iso: str,
    end_iso: Optional[str] = None,
    attendees_emails: Optional[List[str]] = None,
    description: str = "",
    timezone: str = "UTC",
) -> Dict[str, Any]:
    """
    Creates a Calendar event and requests a Meet link.
    Returns the created event resource.
    """
    from googleapiclient.discovery import build
    import uuid

    creds = get_credentials(CALENDAR_SCOPES)
    service = build("calendar", "v3", credentials=creds)

    if not end_iso:
        # default 30 min
        try:
            dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            end_iso = (dt + timedelta(minutes=30)).isoformat()
        except Exception:
            end_iso = start_iso

    body: Dict[str, Any] = {
        "summary": summary,
        "description": description or "",
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    if attendees_emails:
        body["attendees"] = [{"email": e} for e in attendees_emails if e]

    event = (
        service.events()
        .insert(calendarId="primary", body=body, conferenceDataVersion=1, sendUpdates="all")
        .execute()
    )
    return event


def list_events_in_range(
    *,
    time_min_rfc3339: str,
    time_max_rfc3339: str,
    max_results: int = 50,
) -> List[Dict[str, Any]]:
    """List primary calendar events between two RFC3339 instants (single events expanded)."""
    from googleapiclient.discovery import build

    creds = get_credentials(CALENDAR_SCOPES)
    service = build("calendar", "v3", credentials=creds)
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min_rfc3339,
            timeMax=time_max_rfc3339,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return list(events_result.get("items") or [])

