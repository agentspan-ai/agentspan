# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Software Bug Assistant — agent_tool + mcp_tool for bug triage.

Mirrors the pattern from google/adk-samples/software-bug-assistant.
Demonstrates:
    - agent_tool wrapping a search sub-agent
    - mcp_tool for live GitHub issue/PR lookup on conductor-oss/conductor
    - @tool for local ticket CRUD (in-memory store)

Architecture:
    software_assistant (root agent)
      tools:
        - get_current_date()           # @tool
        - agent_tool(search_agent)     # Sub-agent for research
        - mcp_tool(github)             # GitHub issues/PRs via MCP
        - search_tickets()             # @tool (local DB)
        - create_ticket()              # @tool (local DB)
        - update_ticket()              # @tool (local DB)

Requirements:
    - Conductor server with AgentTool + MCP support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
    - GH_TOKEN in .env or environment
"""

import os
from datetime import datetime

from agentspan.agents import Agent, AgentRuntime, agent_tool, tool, mcp_tool

from settings import settings


# ── In-memory ticket store (mirrors real conductor-oss/conductor issues) ──

_tickets: dict[str, dict] = {
    "COND-001": {
        "id": "COND-001",
        "title": "TaskStatusListener not invoked for system task lifecycle transitions",
        "status": "open",
        "priority": "high",
        "github_issue": 847,
        "description": "TaskStatusListener notifications are only fully wired for "
                       "worker tasks (SIMPLE/custom). Both synchronous and asynchronous "
                       "system tasks miss lifecycle transition callbacks.",
        "created": "2026-03-10",
    },
    "COND-002": {
        "id": "COND-002",
        "title": "Support reasonForIncompletion in fail_task event handlers",
        "status": "open",
        "priority": "medium",
        "github_issue": 858,
        "description": "When an event handler uses action: fail_task, there is no way "
                       "to set reasonForIncompletion. Need to support this field so "
                       "failed tasks have meaningful error messages.",
        "created": "2026-03-13",
    },
    "COND-003": {
        "id": "COND-003",
        "title": "Optimize /workflowDefs page: paginate latest-versions API",
        "status": "open",
        "priority": "medium",
        "github_issue": 781,
        "description": "The UI /workflowDefs page calls GET /metadata/workflow which "
                       "returns all versions of all workflows. This causes slow page "
                       "loads. Need pagination for the latest-versions endpoint.",
        "created": "2026-02-18",
    },
}

_next_id = 4


# ── Function tools ────────────────────────────────────────────────

@tool
def get_current_date() -> dict:
    """Get today's date.

    Returns:
        Dictionary with the current date.
    """
    return {"date": datetime.now().strftime("%Y-%m-%d")}


@tool
def search_tickets(query: str) -> dict:
    """Search the internal bug ticket database for Conductor issues.

    Args:
        query: Search term to match against ticket titles and descriptions.

    Returns:
        Dictionary with matching tickets.
    """
    query_lower = query.lower()
    matches = [
        t for t in _tickets.values()
        if query_lower in t["title"].lower() or query_lower in t["description"].lower()
    ]
    return {"query": query, "count": len(matches), "tickets": matches}


@tool
def create_ticket(title: str, description: str, priority: str = "medium") -> dict:
    """Create a new bug ticket in the internal tracker.

    Args:
        title: Short title for the bug.
        description: Detailed description of the issue.
        priority: Priority level (low, medium, high, critical).

    Returns:
        Dictionary with the created ticket.
    """
    global _next_id
    ticket_id = f"COND-{_next_id:03d}"
    _next_id += 1
    ticket = {
        "id": ticket_id,
        "title": title,
        "status": "open",
        "priority": priority,
        "description": description,
        "created": datetime.now().strftime("%Y-%m-%d"),
    }
    _tickets[ticket_id] = ticket
    return {"created": True, "ticket": ticket}


@tool
def update_ticket(ticket_id: str, status: str = "", priority: str = "") -> dict:
    """Update an existing bug ticket's status or priority.

    Args:
        ticket_id: The ticket ID (e.g. COND-001).
        status: New status (open, in_progress, resolved, closed). Leave empty to skip.
        priority: New priority (low, medium, high, critical). Leave empty to skip.

    Returns:
        Dictionary with the updated ticket or error.
    """
    ticket = _tickets.get(ticket_id.upper())
    if not ticket:
        return {"error": f"Ticket {ticket_id} not found"}
    if status:
        ticket["status"] = status
    if priority:
        ticket["priority"] = priority
    return {"updated": True, "ticket": ticket}


# ── Search sub-agent (wrapped as AgentTool) ───────────────────────

@tool
def search_web(query: str) -> dict:
    """Search the web for information about a Conductor bug or workflow issue.

    Args:
        query: The search query.

    Returns:
        Dictionary with search results.
    """
    results = {
        "task status listener": {
            "source": "Conductor Docs",
            "answer": "TaskStatusListener is only wired for SIMPLE tasks. System "
                      "tasks like HTTP, INLINE, SUB_WORKFLOW bypass the listener "
                      "because they complete synchronously within the decider loop.",
        },
        "do_while loop": {
            "source": "GitHub PR #820",
            "answer": "DO_WHILE tasks with 'items' now pass validation without "
                      "loopCondition. Fixed in PR #820 — the validator was "
                      "unconditionally requiring loopCondition for all DO_WHILE tasks.",
        },
        "event handler fail": {
            "source": "GitHub Issue #858",
            "answer": "Event handlers with action: fail_task cannot set "
                      "reasonForIncompletion. A proposed fix adds an optional "
                      "'reason' field to the fail_task action configuration.",
        },
        "workflow def pagination": {
            "source": "GitHub Issue #781",
            "answer": "The /metadata/workflow endpoint returns all versions of all "
                      "workflows causing slow UI loads. A pagination API for "
                      "latest-versions is proposed to fix this.",
        },
    }
    query_lower = query.lower()
    for key, val in results.items():
        if key in query_lower:
            return {"query": query, "found": True, **val}
    return {"query": query, "found": False, "summary": "No specific results found."}


search_agent = Agent(
    name="search_agent",
    model=settings.llm_model,
    instructions=(
        "You are a technical search assistant specializing in Conductor "
        "(conductor-oss/conductor) workflow orchestration. Use the search_web "
        "tool to find relevant information about bugs, errors, and Conductor "
        "configuration issues. Provide concise, actionable answers."
    ),
    tools=[search_web],
)


# ── GitHub MCP tools (live access to conductor-oss/conductor) ─────

github_mcp_url = os.environ.get(
    "GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/"
)
github_token = os.environ.get("GH_TOKEN", "")

github = mcp_tool(
    server_url=github_mcp_url,
    name="github_mcp",
    description="GitHub tools for accessing the conductor-oss/conductor repository — "
                "search issues, list open pull requests, and get issue details",
    headers={"Authorization": f"Bearer {github_token}"},
    tool_names=[
        "search_repositories", "search_issues", "list_issues",
        "get_issue", "list_pull_requests", "get_pull_request",
    ],
)


# ── Root agent ────────────────────────────────────────────────────

software_assistant = Agent(
    name="software_assistant",
    model=settings.llm_model,
    instructions=(
        "You are a software bug triage assistant for the Conductor workflow "
        "orchestration engine (https://github.com/conductor-oss/conductor).\n\n"
        "Your capabilities:\n"
        "1. Search and manage internal bug tickets (search_tickets, create_ticket, "
        "update_ticket)\n"
        "2. Research Conductor issues using the search_agent tool\n"
        "3. Look up real GitHub issues and PRs on conductor-oss/conductor using "
        "the GitHub MCP tools\n"
        "4. Cross-reference GitHub issues with internal tickets\n\n"
        "When triaging:\n"
        "- Use GitHub MCP tools to fetch the latest issues and PRs from "
        "conductor-oss/conductor\n"
        "- Cross-reference with internal tickets (search_tickets)\n"
        "- Research any unfamiliar issues with the search_agent\n"
        "- Create internal tickets for new issues not yet tracked\n"
        "- Suggest next steps, referencing GitHub issue/PR numbers"
    ),
    tools=[
        get_current_date,
        agent_tool(search_agent),
        github,
        search_tickets,
        create_ticket,
        update_ticket,
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        software_assistant,
        "Review the latest open issues and PRs on conductor-oss/conductor. "
        "Check if any of them relate to our internal tickets. "
        "Pay attention to the DO_WHILE fix (PR #820) and the scheduler "
        "persistence PRs. Give me a triage summary.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(software_assistant)
        # CLI alternative:
        # agentspan deploy --package examples.adk.33_software_bug_assistant
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(software_assistant)
