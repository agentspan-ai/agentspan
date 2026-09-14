"""Gmail tools — Gmail API v1 integration."""

from __future__ import annotations

import base64
import os
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool

_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"


def _get_token() -> str:
    token = os.environ.get("GMAIL_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("GMAIL_ACCESS_TOKEN environment variable is not set")
    return token


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/json",
    }


@tool(credentials=["GMAIL_ACCESS_TOKEN"])
def gmail_list_messages(query: str = "", max_results: int = 20) -> List[Dict[str, Any]]:
    """List or search emails in Gmail.

    Args:
        query: Gmail search query (e.g. ``"from:alice subject:meeting"``).
        max_results: Maximum number of messages to return (default 20).

    Returns:
        List of message summaries with ``id`` and ``threadId``.
    """
    _get_token()  # validate credentials
    max_results = min(max(max_results, 1), 100)

    params: Dict[str, Any] = {"maxResults": max_results}
    if query:
        params["q"] = query

    resp = httpx.get(
        f"{_BASE_URL}/messages",
        params=params,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return data.get("messages", [])


@tool(credentials=["GMAIL_ACCESS_TOKEN"])
def gmail_read_message(message_id: str) -> Dict[str, Any]:
    """Read the full content of an email message.

    Args:
        message_id: The Gmail message ID.

    Returns:
        Dict with ``id``, ``snippet``, ``subject``, ``from``, ``to``, ``body``.
    """
    if not message_id:
        raise ValueError("message_id is required")

    resp = httpx.get(
        f"{_BASE_URL}/messages/{message_id}",
        params={"format": "full"},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    msg = resp.json()
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    body = ""
    payload = msg.get("payload", {})
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                break

    return {
        "id": msg.get("id", ""),
        "snippet": msg.get("snippet", ""),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "body": body,
    }


@tool(credentials=["GMAIL_ACCESS_TOKEN"])
def gmail_send_message(to: str, subject: str, body: str) -> Dict[str, str]:
    """Send an email via Gmail.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text email body.

    Returns:
        Dict with ``id`` and ``threadId`` of the sent message.
    """
    if not to:
        raise ValueError("to is required")
    if not subject:
        raise ValueError("subject is required")

    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    resp = httpx.post(
        f"{_BASE_URL}/messages/send",
        json={"raw": raw},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"id": data.get("id", ""), "threadId": data.get("threadId", "")}


@tool(credentials=["GMAIL_ACCESS_TOKEN"])
def gmail_search(query: str) -> List[Dict[str, Any]]:
    """Search emails with Gmail query syntax.

    Args:
        query: Gmail search query (e.g. ``"is:unread from:boss"``).

    Returns:
        List of matching message summaries.
    """
    if not query:
        raise ValueError("query is required")
    return gmail_list_messages(query=query, max_results=20)


def get_tools() -> List[Any]:
    """Return all gmail tools."""
    return [gmail_list_messages, gmail_read_message, gmail_send_message, gmail_search]
