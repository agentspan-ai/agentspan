"""Google Calendar integration tools — event listing, creation, and search."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool

_BASE_URL = "https://www.googleapis.com/calendar/v3"


def _gcal_headers() -> Dict[str, str]:
    """Return headers for Google Calendar API, raising if token is missing."""
    token = os.environ.get("GOOGLE_CALENDAR_TOKEN", "")
    if not token:
        raise RuntimeError("GOOGLE_CALENDAR_TOKEN environment variable is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _format_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant fields from a calendar event."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "start": start.get("dateTime", start.get("date", "")),
        "end": end.get("dateTime", end.get("date", "")),
        "html_link": event.get("htmlLink", ""),
        "status": event.get("status", ""),
    }


@tool(credentials=["GOOGLE_CALENDAR_TOKEN"])
def gcal_list_events(days_ahead: int = 7) -> List[Dict[str, Any]]:
    """List upcoming Google Calendar events.

    Args:
        days_ahead: Number of days ahead to look (default 7).

    Returns:
        List of event dicts with ``id``, ``summary``, ``description``,
        ``start``, ``end``, ``html_link``, and ``status`` keys.
    """
    headers = _gcal_headers()
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    resp = httpx.get(
        f"{_BASE_URL}/calendars/primary/events",
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        },
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()

    return [_format_event(e) for e in resp.json().get("items", [])]


@tool(credentials=["GOOGLE_CALENDAR_TOKEN"])
def gcal_create_event(
    summary: str, start: str, end: str, description: str = ""
) -> Dict[str, Any]:
    """Create a new Google Calendar event.

    Args:
        summary: Event title.
        start: Start time in ISO 8601 format (e.g. ``"2025-01-15T09:00:00-05:00"``).
        end: End time in ISO 8601 format.
        description: Optional event description.

    Returns:
        Created event dict with ``id``, ``summary``, ``start``, ``end``,
        ``html_link``, and ``status`` keys.
    """
    headers = {**_gcal_headers(), "Content-Type": "application/json"}

    body: Dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        body["description"] = description

    resp = httpx.post(
        f"{_BASE_URL}/calendars/primary/events",
        json=body,
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()

    return _format_event(resp.json())


@tool(credentials=["GOOGLE_CALENDAR_TOKEN"])
def gcal_search_events(query: str) -> List[Dict[str, Any]]:
    """Search Google Calendar events by text query.

    Args:
        query: Free-text search query.

    Returns:
        List of matching event dicts.
    """
    headers = _gcal_headers()

    resp = httpx.get(
        f"{_BASE_URL}/calendars/primary/events",
        params={
            "q": query,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 20,
        },
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()

    return [_format_event(e) for e in resp.json().get("items", [])]


def get_tools() -> List[Any]:
    """Return all Google Calendar tools."""
    return [gcal_list_events, gcal_create_event, gcal_search_events]
