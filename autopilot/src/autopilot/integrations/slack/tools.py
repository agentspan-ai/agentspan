"""Slack integration tools — messaging and channel operations via Slack Web API."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool

_BASE_URL = "https://slack.com/api"


def _slack_headers() -> Dict[str, str]:
    """Return headers for Slack API requests, raising if token is missing."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN environment variable is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _check_slack_response(data: Dict[str, Any]) -> None:
    """Raise if the Slack API response indicates an error."""
    if not data.get("ok"):
        error = data.get("error", "unknown_error")
        raise RuntimeError(f"Slack API error: {error}")


@tool(credentials=["SLACK_BOT_TOKEN"])
def slack_send_message(channel: str, text: str) -> Dict[str, Any]:
    """Send a message to a Slack channel.

    Args:
        channel: Channel ID or name (e.g. ``"C01234ABCDE"`` or ``"#general"``).
        text: Message text to send.

    Returns:
        Dict with ``ok``, ``channel``, ``ts`` (timestamp), and ``message`` keys.
    """
    headers = _slack_headers()
    resp = httpx.post(
        f"{_BASE_URL}/chat.postMessage",
        json={"channel": channel, "text": text},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _check_slack_response(data)
    return {
        "ok": data.get("ok"),
        "channel": data.get("channel", ""),
        "ts": data.get("ts", ""),
        "message": data.get("message", {}),
    }


@tool(credentials=["SLACK_BOT_TOKEN"])
def slack_list_channels() -> List[Dict[str, Any]]:
    """List Slack channels the bot is a member of.

    Returns:
        List of dicts with ``id``, ``name``, ``is_private``, and ``num_members`` keys.
    """
    headers = _slack_headers()
    resp = httpx.get(
        f"{_BASE_URL}/conversations.list",
        params={"types": "public_channel,private_channel", "limit": 100},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _check_slack_response(data)

    results: List[Dict[str, Any]] = []
    for ch in data.get("channels", []):
        results.append({
            "id": ch.get("id", ""),
            "name": ch.get("name", ""),
            "is_private": ch.get("is_private", False),
            "num_members": ch.get("num_members", 0),
        })
    return results


@tool(credentials=["SLACK_BOT_TOKEN"])
def slack_read_messages(channel: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Read recent messages from a Slack channel.

    Args:
        channel: Channel ID (e.g. ``"C01234ABCDE"``).
        limit: Number of messages to retrieve (default 10, max 100).

    Returns:
        List of dicts with ``ts``, ``user``, ``text``, and ``type`` keys.
    """
    headers = _slack_headers()
    limit = min(max(limit, 1), 100)
    resp = httpx.get(
        f"{_BASE_URL}/conversations.history",
        params={"channel": channel, "limit": limit},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _check_slack_response(data)

    results: List[Dict[str, Any]] = []
    for msg in data.get("messages", []):
        results.append({
            "ts": msg.get("ts", ""),
            "user": msg.get("user", ""),
            "text": msg.get("text", ""),
            "type": msg.get("type", ""),
        })
    return results


@tool(credentials=["SLACK_BOT_TOKEN"])
def slack_search_messages(query: str) -> List[Dict[str, Any]]:
    """Search messages across Slack.

    Args:
        query: Search query string.

    Returns:
        List of dicts with ``text``, ``username``, ``channel``,
        ``ts``, and ``permalink`` keys.
    """
    headers = _slack_headers()
    resp = httpx.get(
        f"{_BASE_URL}/search.messages",
        params={"query": query, "count": 20},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _check_slack_response(data)

    results: List[Dict[str, Any]] = []
    for match in data.get("messages", {}).get("matches", []):
        results.append({
            "text": match.get("text", ""),
            "username": match.get("username", ""),
            "channel": match.get("channel", {}).get("name", ""),
            "ts": match.get("ts", ""),
            "permalink": match.get("permalink", ""),
        })
    return results


def get_tools() -> List[Any]:
    """Return all Slack tools."""
    return [slack_send_message, slack_list_channels, slack_read_messages, slack_search_messages]
