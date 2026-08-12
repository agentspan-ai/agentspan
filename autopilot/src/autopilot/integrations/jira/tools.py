"""Jira tools — Jira REST API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool


def _get_credentials() -> tuple[str, str, str]:
    url = os.environ.get("JIRA_URL", "")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")

    missing = []
    if not url:
        missing.append("JIRA_URL")
    if not email:
        missing.append("JIRA_EMAIL")
    if not token:
        missing.append("JIRA_API_TOKEN")

    if missing:
        raise RuntimeError(f"{', '.join(missing)} environment variable(s) not set")
    return url.rstrip("/"), email, token


def _auth() -> httpx.BasicAuth:
    _, email, token = _get_credentials()
    return httpx.BasicAuth(email, token)


def _base_url() -> str:
    url, _, _ = _get_credentials()
    return f"{url}/rest/api/3"


@tool(credentials=["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def jira_search(jql: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """Search Jira issues using JQL.

    Args:
        jql: JQL query string (e.g. ``"project = ENG AND status = Open"``).
        max_results: Maximum number of results (default 20).

    Returns:
        List of issue objects with ``key``, ``summary``, ``status``, ``assignee``.
    """
    if not jql:
        raise ValueError("jql is required")
    max_results = min(max(max_results, 1), 100)

    resp = httpx.get(
        f"{_base_url()}/search",
        params={"jql": jql, "maxResults": max_results},
        auth=_auth(),
        headers={"Accept": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    results = []
    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        results.append({
            "key": issue.get("key", ""),
            "summary": fields.get("summary", ""),
            "status": fields.get("status", {}).get("name", ""),
            "assignee": (fields.get("assignee") or {}).get("displayName", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
        })
    return results


@tool(credentials=["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def jira_get_issue(issue_key: str) -> Dict[str, Any]:
    """Get full details of a Jira issue.

    Args:
        issue_key: The issue key (e.g. ``"ENG-123"``).

    Returns:
        Issue object with full field details.
    """
    if not issue_key:
        raise ValueError("issue_key is required")

    resp = httpx.get(
        f"{_base_url()}/issue/{issue_key}",
        auth=_auth(),
        headers={"Accept": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    fields = data.get("fields", {})
    return {
        "key": data.get("key", ""),
        "summary": fields.get("summary", ""),
        "description": fields.get("description", ""),
        "status": fields.get("status", {}).get("name", ""),
        "assignee": (fields.get("assignee") or {}).get("displayName", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "created": fields.get("created", ""),
        "updated": fields.get("updated", ""),
    }


@tool(credentials=["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def jira_create_issue(
    project_key: str, summary: str, description: str = "", issue_type: str = "Task"
) -> Dict[str, str]:
    """Create a new Jira issue.

    Args:
        project_key: Project key (e.g. ``"ENG"``).
        summary: Issue summary.
        description: Issue description.
        issue_type: Issue type name (default ``"Task"``).

    Returns:
        Dict with ``key`` and ``id`` of the created issue.
    """
    if not project_key:
        raise ValueError("project_key is required")
    if not summary:
        raise ValueError("summary is required")

    payload: Dict[str, Any] = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
    }
    if description:
        payload["fields"]["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                }
            ],
        }

    resp = httpx.post(
        f"{_base_url()}/issue",
        json=payload,
        auth=_auth(),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"key": data.get("key", ""), "id": data.get("id", "")}


@tool(credentials=["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def jira_update_issue(issue_key: str, fields: Dict[str, Any]) -> str:
    """Update fields on an existing Jira issue.

    Args:
        issue_key: The issue key (e.g. ``"ENG-123"``).
        fields: Dict of field names to new values.

    Returns:
        Confirmation message.
    """
    if not issue_key:
        raise ValueError("issue_key is required")
    if not fields:
        raise ValueError("fields is required")

    resp = httpx.put(
        f"{_base_url()}/issue/{issue_key}",
        json={"fields": fields},
        auth=_auth(),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return f"Updated {issue_key}"


@tool(credentials=["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def jira_add_comment(issue_key: str, body: str) -> Dict[str, str]:
    """Add a comment to a Jira issue.

    Args:
        issue_key: The issue key (e.g. ``"ENG-123"``).
        body: Comment text.

    Returns:
        Dict with ``id`` of the created comment.
    """
    if not issue_key:
        raise ValueError("issue_key is required")
    if not body:
        raise ValueError("body is required")

    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body}],
                }
            ],
        }
    }

    resp = httpx.post(
        f"{_base_url()}/issue/{issue_key}/comment",
        json=payload,
        auth=_auth(),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"id": data.get("id", "")}


def get_tools() -> List[Any]:
    """Return all jira tools."""
    return [jira_search, jira_get_issue, jira_create_issue, jira_update_issue, jira_add_comment]
