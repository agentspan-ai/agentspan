"""Notion tools — Notion API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool

_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _get_api_key() -> str:
    key = os.environ.get("NOTION_API_KEY", "")
    if not key:
        raise RuntimeError("NOTION_API_KEY environment variable is not set")
    return key


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
        "Notion-Version": _NOTION_VERSION,
    }


@tool(credentials=["NOTION_API_KEY"])
def notion_search(query: str) -> List[Dict[str, Any]]:
    """Search pages and databases in Notion.

    Args:
        query: Search query text.

    Returns:
        List of result objects with ``id``, ``type``, ``title``, ``url``.
    """
    if not query:
        raise ValueError("query is required")

    resp = httpx.post(
        f"{_BASE_URL}/search",
        json={"query": query, "page_size": 20},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    results = []
    for item in data.get("results", []):
        title = ""
        props = item.get("properties", {})
        if "title" in props:
            title_parts = props["title"].get("title", [])
            if title_parts:
                title = title_parts[0].get("plain_text", "")
        elif "Name" in props:
            name_parts = props["Name"].get("title", [])
            if name_parts:
                title = name_parts[0].get("plain_text", "")

        results.append({
            "id": item.get("id", ""),
            "type": item.get("object", ""),
            "title": title,
            "url": item.get("url", ""),
        })
    return results


@tool(credentials=["NOTION_API_KEY"])
def notion_read_page(page_id: str) -> str:
    """Read a Notion page's content as text.

    Args:
        page_id: The Notion page ID.

    Returns:
        Page content as plain text.
    """
    if not page_id:
        raise ValueError("page_id is required")

    resp = httpx.get(
        f"{_BASE_URL}/blocks/{page_id}/children",
        params={"page_size": 100},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    text_parts: List[str] = []

    for block in data.get("results", []):
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})
        rich_text = block_data.get("rich_text", [])
        for rt in rich_text:
            text_parts.append(rt.get("plain_text", ""))
        if block_type in ("heading_1", "heading_2", "heading_3", "paragraph"):
            text_parts.append("\n")

    return "".join(text_parts).strip()


@tool(credentials=["NOTION_API_KEY"])
def notion_query_database(
    database_id: str, filter: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Query a Notion database.

    Args:
        database_id: The Notion database ID.
        filter: Optional Notion filter object.

    Returns:
        List of page objects from the database.
    """
    if not database_id:
        raise ValueError("database_id is required")

    payload: Dict[str, Any] = {"page_size": 100}
    if filter:
        payload["filter"] = filter

    resp = httpx.post(
        f"{_BASE_URL}/databases/{database_id}/query",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return data.get("results", [])


@tool(credentials=["NOTION_API_KEY"])
def notion_create_page(
    parent_id: str, title: str, content: str = ""
) -> Dict[str, str]:
    """Create a new page in Notion.

    Args:
        parent_id: Parent page or database ID.
        title: Page title.
        content: Optional page content (plain text).

    Returns:
        Dict with ``id`` and ``url`` of the created page.
    """
    if not parent_id:
        raise ValueError("parent_id is required")
    if not title:
        raise ValueError("title is required")

    children: List[Dict[str, Any]] = []
    if content:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": content}}]
            },
        })

    payload: Dict[str, Any] = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
    }
    if children:
        payload["children"] = children

    resp = httpx.post(
        f"{_BASE_URL}/pages",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"id": data.get("id", ""), "url": data.get("url", "")}


def get_tools() -> List[Any]:
    """Return all notion tools."""
    return [notion_search, notion_read_page, notion_query_database, notion_create_page]
