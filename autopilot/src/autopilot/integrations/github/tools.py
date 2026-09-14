"""GitHub integration tools — repository, issue, and PR operations via REST API."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool

_BASE_URL = "https://api.github.com"


def _github_headers() -> Dict[str, str]:
    """Return headers for GitHub API requests, raising if token is missing."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is not set")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@tool(credentials=["GITHUB_TOKEN"])
def github_search_repos(query: str) -> List[Dict[str, Any]]:
    """Search GitHub repositories.

    Args:
        query: Search query string (e.g. ``"language:python stars:>100"``).

    Returns:
        List of dicts with ``name``, ``full_name``, ``description``,
        ``html_url``, ``stargazers_count``, and ``language`` keys.
    """
    resp = httpx.get(
        f"{_BASE_URL}/search/repositories",
        params={"q": query, "per_page": 10},
        headers={"Accept": "application/vnd.github+json"},
        timeout=15.0,
    )
    resp.raise_for_status()

    results: List[Dict[str, Any]] = []
    for item in resp.json().get("items", []):
        results.append({
            "name": item.get("name", ""),
            "full_name": item.get("full_name", ""),
            "description": item.get("description", ""),
            "html_url": item.get("html_url", ""),
            "stargazers_count": item.get("stargazers_count", 0),
            "language": item.get("language", ""),
        })
    return results


@tool(credentials=["GITHUB_TOKEN"])
def github_list_issues(owner: str, repo: str, state: str = "open") -> List[Dict[str, Any]]:
    """List issues for a GitHub repository.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        state: Issue state filter — ``"open"``, ``"closed"``, or ``"all"``.

    Returns:
        List of dicts with ``number``, ``title``, ``state``, ``user``,
        ``html_url``, and ``created_at`` keys.
    """
    resp = httpx.get(
        f"{_BASE_URL}/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": 30},
        headers=_github_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    results: List[Dict[str, Any]] = []
    for item in resp.json():
        results.append({
            "number": item.get("number"),
            "title": item.get("title", ""),
            "state": item.get("state", ""),
            "user": item.get("user", {}).get("login", ""),
            "html_url": item.get("html_url", ""),
            "created_at": item.get("created_at", ""),
        })
    return results


@tool(credentials=["GITHUB_TOKEN"])
def github_get_issue(owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
    """Get details for a specific GitHub issue.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        issue_number: The issue number.

    Returns:
        Dict with ``number``, ``title``, ``state``, ``body``, ``user``,
        ``html_url``, ``labels``, and ``created_at`` keys.
    """
    resp = httpx.get(
        f"{_BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}",
        headers=_github_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    item = resp.json()
    return {
        "number": item.get("number"),
        "title": item.get("title", ""),
        "state": item.get("state", ""),
        "body": item.get("body", ""),
        "user": item.get("user", {}).get("login", ""),
        "html_url": item.get("html_url", ""),
        "labels": [lbl.get("name", "") for lbl in item.get("labels", [])],
        "created_at": item.get("created_at", ""),
    }


@tool(credentials=["GITHUB_TOKEN"])
def github_create_issue(owner: str, repo: str, title: str, body: str) -> Dict[str, Any]:
    """Create a new issue on a GitHub repository.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        title: Issue title.
        body: Issue body (Markdown).

    Returns:
        Dict with ``number``, ``title``, ``html_url``, and ``created_at`` keys.
    """
    resp = httpx.post(
        f"{_BASE_URL}/repos/{owner}/{repo}/issues",
        json={"title": title, "body": body},
        headers=_github_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    item = resp.json()
    return {
        "number": item.get("number"),
        "title": item.get("title", ""),
        "html_url": item.get("html_url", ""),
        "created_at": item.get("created_at", ""),
    }


@tool(credentials=["GITHUB_TOKEN"])
def github_list_prs(owner: str, repo: str, state: str = "open") -> List[Dict[str, Any]]:
    """List pull requests for a GitHub repository.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        state: PR state filter — ``"open"``, ``"closed"``, or ``"all"``.

    Returns:
        List of dicts with ``number``, ``title``, ``state``, ``user``,
        ``html_url``, and ``created_at`` keys.
    """
    resp = httpx.get(
        f"{_BASE_URL}/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": 30},
        headers=_github_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    results: List[Dict[str, Any]] = []
    for item in resp.json():
        results.append({
            "number": item.get("number"),
            "title": item.get("title", ""),
            "state": item.get("state", ""),
            "user": item.get("user", {}).get("login", ""),
            "html_url": item.get("html_url", ""),
            "created_at": item.get("created_at", ""),
        })
    return results


@tool(credentials=["GITHUB_TOKEN"])
def github_get_pr(owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
    """Get details for a specific pull request, including the diff.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        pr_number: The pull request number.

    Returns:
        Dict with ``number``, ``title``, ``state``, ``body``, ``user``,
        ``html_url``, ``diff``, ``merged``, and ``created_at`` keys.
    """
    headers = _github_headers()

    # Fetch PR metadata
    resp = httpx.get(
        f"{_BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    item = resp.json()

    # Fetch diff
    diff_headers = {**headers, "Accept": "application/vnd.github.diff"}
    diff_resp = httpx.get(
        f"{_BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers=diff_headers,
        timeout=15.0,
    )
    diff_resp.raise_for_status()

    return {
        "number": item.get("number"),
        "title": item.get("title", ""),
        "state": item.get("state", ""),
        "body": item.get("body", ""),
        "user": item.get("user", {}).get("login", ""),
        "html_url": item.get("html_url", ""),
        "diff": diff_resp.text,
        "merged": item.get("merged", False),
        "created_at": item.get("created_at", ""),
    }


def get_tools() -> List[Any]:
    """Return all GitHub tools."""
    return [
        github_search_repos,
        github_list_issues,
        github_get_issue,
        github_create_issue,
        github_list_prs,
        github_get_pr,
    ]
