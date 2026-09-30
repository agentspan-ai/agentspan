"""Linear tools — Linear GraphQL API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool

_GRAPHQL_URL = "https://api.linear.app/graphql"


def _get_api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "")
    if not key:
        raise RuntimeError("LINEAR_API_KEY environment variable is not set")
    return key


def _headers() -> Dict[str, str]:
    return {
        "Authorization": _get_api_key(),
        "Content-Type": "application/json",
    }


def _graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute a GraphQL query against the Linear API."""
    payload: Dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = httpx.post(
        _GRAPHQL_URL,
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Linear GraphQL error: {data['errors']}")
    return data.get("data", {})


@tool(credentials=["LINEAR_API_KEY"])
def linear_list_issues(team_key: Optional[str] = None, state: Optional[str] = None) -> List[Dict[str, Any]]:
    """List issues from Linear.

    Args:
        team_key: Optional team key to filter by (e.g. ``"ENG"``).
        state: Optional state name to filter by (e.g. ``"In Progress"``).

    Returns:
        List of issue objects with ``id``, ``title``, ``state``, ``priority``.
    """
    _get_api_key()

    filters: List[str] = []
    if team_key:
        filters.append(f'team: {{ key: {{ eq: "{team_key}" }} }}')
    if state:
        filters.append(f'state: {{ name: {{ eq: "{state}" }} }}')

    filter_str = ", ".join(filters)
    filter_clause = f"(filter: {{ {filter_str} }})" if filters else ""

    query = f"""
    query {{
        issues{filter_clause} {{
            nodes {{
                id
                title
                identifier
                priority
                state {{ name }}
                assignee {{ name }}
            }}
        }}
    }}
    """

    data = _graphql(query)
    nodes = data.get("issues", {}).get("nodes", [])
    return [
        {
            "id": n["id"],
            "title": n["title"],
            "identifier": n.get("identifier", ""),
            "priority": n.get("priority", 0),
            "state": n.get("state", {}).get("name", ""),
            "assignee": (n.get("assignee") or {}).get("name", ""),
        }
        for n in nodes
    ]


@tool(credentials=["LINEAR_API_KEY"])
def linear_get_issue(issue_id: str) -> Dict[str, Any]:
    """Get details of a specific Linear issue.

    Args:
        issue_id: The Linear issue ID.

    Returns:
        Issue object with full details.
    """
    if not issue_id:
        raise ValueError("issue_id is required")

    query = """
    query($id: String!) {
        issue(id: $id) {
            id
            title
            identifier
            description
            priority
            state { name }
            assignee { name }
            labels { nodes { name } }
            createdAt
            updatedAt
        }
    }
    """
    data = _graphql(query, {"id": issue_id})
    return data.get("issue", {})


@tool(credentials=["LINEAR_API_KEY"])
def linear_create_issue(
    team_key: str, title: str, description: str = "", priority: int = 0
) -> Dict[str, str]:
    """Create a new issue in Linear.

    Args:
        team_key: Team key (e.g. ``"ENG"``).
        title: Issue title.
        description: Issue description (markdown).
        priority: Priority level (0=none, 1=urgent, 2=high, 3=medium, 4=low).

    Returns:
        Dict with ``id`` and ``identifier`` of the created issue.
    """
    if not team_key:
        raise ValueError("team_key is required")
    if not title:
        raise ValueError("title is required")

    # First, resolve team key to team ID
    team_query = """
    query($key: String!) {
        teams(filter: { key: { eq: $key } }) {
            nodes { id }
        }
    }
    """
    team_data = _graphql(team_query, {"key": team_key})
    teams = team_data.get("teams", {}).get("nodes", [])
    if not teams:
        raise RuntimeError(f"Team not found: {team_key}")
    team_id = teams[0]["id"]

    mutation = """
    mutation($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { id identifier title }
        }
    }
    """
    variables = {
        "input": {
            "teamId": team_id,
            "title": title,
            "description": description,
            "priority": priority,
        }
    }
    data = _graphql(mutation, variables)
    issue = data.get("issueCreate", {}).get("issue", {})
    return {"id": issue.get("id", ""), "identifier": issue.get("identifier", "")}


@tool(credentials=["LINEAR_API_KEY"])
def linear_update_issue(
    issue_id: str, state: Optional[str] = None, assignee: Optional[str] = None
) -> Dict[str, Any]:
    """Update an existing Linear issue.

    Args:
        issue_id: The Linear issue ID.
        state: New state name (e.g. ``"Done"``).
        assignee: New assignee email or name.

    Returns:
        Updated issue summary.
    """
    if not issue_id:
        raise ValueError("issue_id is required")

    input_fields: Dict[str, Any] = {}

    if state:
        # Resolve state name to ID
        state_query = """
        query($name: String!) {
            workflowStates(filter: { name: { eq: $name } }) {
                nodes { id }
            }
        }
        """
        state_data = _graphql(state_query, {"name": state})
        states = state_data.get("workflowStates", {}).get("nodes", [])
        if states:
            input_fields["stateId"] = states[0]["id"]

    if assignee:
        input_fields["assigneeId"] = assignee

    mutation = """
    mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue { id title identifier state { name } }
        }
    }
    """
    data = _graphql(mutation, {"id": issue_id, "input": input_fields})
    return data.get("issueUpdate", {}).get("issue", {})


def get_tools() -> List[Any]:
    """Return all linear tools."""
    return [linear_list_issues, linear_get_issue, linear_create_issue, linear_update_issue]
