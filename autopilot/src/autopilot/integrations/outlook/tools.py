"""Outlook tools — Microsoft Graph API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool

_BASE_URL = "https://graph.microsoft.com/v1.0/me"


def _get_token() -> str:
    token = os.environ.get("OUTLOOK_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("OUTLOOK_ACCESS_TOKEN environment variable is not set")
    return token


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


@tool(credentials=["OUTLOOK_ACCESS_TOKEN"])
def outlook_list_messages(folder: str = "inbox", top: int = 20) -> List[Dict[str, Any]]:
    """List emails in a mailbox folder.

    Args:
        folder: Mail folder name (default ``"inbox"``).
        top: Maximum number of messages to return (default 20).

    Returns:
        List of message objects with ``id``, ``subject``, ``from``, ``receivedDateTime``.
    """
    _get_token()
    top = min(max(top, 1), 100)

    resp = httpx.get(
        f"{_BASE_URL}/mailFolders/{folder}/messages",
        params={"$top": top, "$select": "id,subject,from,receivedDateTime,bodyPreview"},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return data.get("value", [])


@tool(credentials=["OUTLOOK_ACCESS_TOKEN"])
def outlook_read_message(message_id: str) -> Dict[str, Any]:
    """Read the full content of an email.

    Args:
        message_id: The Outlook message ID.

    Returns:
        Message object with ``id``, ``subject``, ``from``, ``body``, ``receivedDateTime``.
    """
    if not message_id:
        raise ValueError("message_id is required")

    resp = httpx.get(
        f"{_BASE_URL}/messages/{message_id}",
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@tool(credentials=["OUTLOOK_ACCESS_TOKEN"])
def outlook_send_message(to: str, subject: str, body: str) -> str:
    """Send an email via Outlook.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body (plain text).

    Returns:
        Confirmation message.
    """
    if not to:
        raise ValueError("to is required")
    if not subject:
        raise ValueError("subject is required")

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
    }

    resp = httpx.post(
        f"{_BASE_URL}/sendMail",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return f"Email sent to {to}"


@tool(credentials=["OUTLOOK_ACCESS_TOKEN"])
def outlook_search(query: str) -> List[Dict[str, Any]]:
    """Search emails using Microsoft Graph search syntax.

    Args:
        query: Search query string.

    Returns:
        List of matching messages.
    """
    if not query:
        raise ValueError("query is required")

    resp = httpx.get(
        f"{_BASE_URL}/messages",
        params={"$search": f'"{query}"', "$top": 20},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return data.get("value", [])


def get_tools() -> List[Any]:
    """Return all outlook tools."""
    return [outlook_list_messages, outlook_read_message, outlook_send_message, outlook_search]
