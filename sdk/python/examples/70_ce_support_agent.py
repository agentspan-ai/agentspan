"""Customer Engineering Support Agent.

Takes a Zendesk ticket number and investigates across Zendesk, JIRA, HubSpot,
Notion (runbooks), and GitHub to produce a solution with a priority rating.

Required environment variables:

    ZENDESK_SUBDOMAIN    – e.g. "mycompany"
    ZENDESK_EMAIL        – admin email for API auth
    ZENDESK_API_TOKEN    – Zendesk API token

    JIRA_BASE_URL        – e.g. "https://mycompany.atlassian.net"
    JIRA_EMAIL           – Atlassian account email
    JIRA_API_TOKEN       – Atlassian API token

    HUBSPOT_ACCESS_TOKEN – HubSpot private app access token

    NOTION_API_KEY       – Notion integration token
    NOTION_RUNBOOK_DB_ID – Database ID of the runbooks database in Notion

    GITHUB_ORG           – GitHub organization name (e.g. "agentspan-dev")

    AGENT_LLM_MODEL      – (optional) LLM model, defaults to openai/gpt-4o-mini

Prerequisites:
    - gh CLI installed and authenticated (`gh auth login`)
    - Conductor server running (`agentspan server start`)

Usage:

    python 70_ce_support_agent.py 12345          # ticket number
    python 70_ce_support_agent.py 12345 --stream  # with real-time events
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional

import requests
from agentspan.agents import (
    Agent,
    AgentRuntime,
    RegexGuardrail,
    agent_tool,
    tool,
)

from settings import settings


# ---------------------------------------------------------------------------
# Zendesk tools
# ---------------------------------------------------------------------------

ZENDESK_SUBDOMAIN = os.environ.get("ZENDESK_SUBDOMAIN", "")
ZENDESK_EMAIL = os.environ.get("ZENDESK_EMAIL", "")
ZENDESK_API_TOKEN = os.environ.get("ZENDESK_API_TOKEN", "")


def _zendesk_headers() -> dict:
    return {"Content-Type": "application/json"}


def _zendesk_auth() -> tuple:
    return (f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN)


def _require_zendesk() -> None:
    if not ZENDESK_SUBDOMAIN or not ZENDESK_EMAIL or not ZENDESK_API_TOKEN:
        raise ValueError("Missing Zendesk config. Set ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, and ZENDESK_API_TOKEN.")


@tool
def get_zendesk_ticket(ticket_id: str) -> dict:
    """Fetch a Zendesk support ticket by its ID.

    Returns ticket subject, description, status, priority, tags,
    requester info, and recent comments.
    """
    _require_zendesk()
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}.json"
    resp = requests.get(url, auth=_zendesk_auth(), headers=_zendesk_headers(), timeout=15)
    resp.raise_for_status()
    ticket = resp.json()["ticket"]

    # Fetch comments for full conversation thread
    comments_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}/comments.json"
    comments_resp = requests.get(comments_url, auth=_zendesk_auth(), headers=_zendesk_headers(), timeout=15)
    comments = []
    if comments_resp.ok:
        comments = [
            {"author_id": c["author_id"], "body": c["body"][:2000], "created_at": c["created_at"]}
            for c in comments_resp.json().get("comments", [])[-10:]  # last 10 comments
        ]

    # Fetch requester details
    requester = {}
    if ticket.get("requester_id"):
        user_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/users/{ticket['requester_id']}.json"
        user_resp = requests.get(user_url, auth=_zendesk_auth(), headers=_zendesk_headers(), timeout=10)
        if user_resp.ok:
            u = user_resp.json()["user"]
            requester = {"name": u.get("name"), "email": u.get("email"), "organization_id": u.get("organization_id")}

    return {
        "id": ticket["id"],
        "subject": ticket.get("subject"),
        "description": ticket.get("description", "")[:3000],
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "tags": ticket.get("tags", []),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "requester": requester,
        "comments": comments,
    }


@tool
def search_zendesk_tickets(query: str) -> dict:
    """Search Zendesk for tickets matching a query.

    Use this to find similar or related tickets from other customers.
    Returns up to 10 results.
    """
    _require_zendesk()
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/search.json"
    params = {"query": f"type:ticket {query}", "per_page": 10}
    resp = requests.get(url, auth=_zendesk_auth(), headers=_zendesk_headers(), params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return {
        "count": len(results),
        "tickets": [
            {
                "id": t["id"],
                "subject": t.get("subject"),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "created_at": t.get("created_at"),
                "description": (t.get("description") or "")[:500],
            }
            for t in results
        ],
    }


# ---------------------------------------------------------------------------
# JIRA tools
# ---------------------------------------------------------------------------

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")


def _jira_auth() -> tuple:
    return (JIRA_EMAIL, JIRA_API_TOKEN)


def _jira_headers() -> dict:
    return {"Accept": "application/json", "Content-Type": "application/json"}


def _require_jira() -> None:
    if not JIRA_BASE_URL or not JIRA_EMAIL or not JIRA_API_TOKEN:
        raise ValueError("Missing JIRA config. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.")


@tool
def search_jira_issues(jql: str) -> dict:
    """Search JIRA issues using JQL (JIRA Query Language).

    Examples:
      - 'text ~ "timeout error" ORDER BY created DESC'
      - 'project = ENG AND labels = customer-reported'
      - 'summary ~ "auth" AND status != Done'

    Returns up to 15 matching issues with key, summary, status, assignee, and priority.
    """
    _require_jira()
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"
    params = {
        "jql": jql,
        "maxResults": 15,
        "fields": "summary,status,assignee,priority,labels,created,updated,description",
    }
    resp = requests.get(url, auth=_jira_auth(), headers=_jira_headers(), params=params, timeout=15)
    resp.raise_for_status()
    issues = resp.json().get("issues", [])
    return {
        "total": resp.json().get("total", 0),
        "issues": [
            {
                "key": i["key"],
                "summary": i["fields"].get("summary"),
                "status": i["fields"].get("status", {}).get("name"),
                "priority": i["fields"].get("priority", {}).get("name"),
                "assignee": (i["fields"].get("assignee") or {}).get("displayName"),
                "labels": i["fields"].get("labels", []),
                "created": i["fields"].get("created"),
                "description": (i["fields"].get("description") or "")[:1000] if isinstance(i["fields"].get("description"), str) else "",
            }
            for i in issues
        ],
    }


@tool
def get_jira_issue(issue_key: str) -> dict:
    """Get full details of a specific JIRA issue by its key (e.g. ENG-1234).

    Returns summary, description, status, comments, and linked issues.
    """
    _require_jira()
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    params = {"fields": "summary,status,assignee,priority,labels,description,comment,issuelinks,created,updated,resolution"}
    resp = requests.get(url, auth=_jira_auth(), headers=_jira_headers(), params=params, timeout=15)
    resp.raise_for_status()
    issue = resp.json()
    fields = issue["fields"]

    comments = []
    for c in (fields.get("comment", {}).get("comments", []) or [])[-5:]:
        body = c.get("body", "")
        if isinstance(body, dict):
            # Atlassian Document Format — extract text nodes
            body = json.dumps(body)[:1000]
        comments.append({"author": c.get("author", {}).get("displayName"), "body": str(body)[:1000], "created": c.get("created")})

    links = []
    for link in fields.get("issuelinks", []):
        linked = link.get("outwardIssue") or link.get("inwardIssue")
        if linked:
            links.append({"key": linked["key"], "summary": linked["fields"].get("summary"), "type": link.get("type", {}).get("name")})

    desc = fields.get("description", "")
    if isinstance(desc, dict):
        desc = json.dumps(desc)[:2000]

    return {
        "key": issue["key"],
        "summary": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "priority": fields.get("priority", {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "labels": fields.get("labels", []),
        "resolution": (fields.get("resolution") or {}).get("name"),
        "description": str(desc)[:2000],
        "comments": comments,
        "linked_issues": links,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
    }


# ---------------------------------------------------------------------------
# HubSpot tools
# ---------------------------------------------------------------------------

HUBSPOT_ACCESS_TOKEN = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")


def _hubspot_headers() -> dict:
    return {"Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}", "Content-Type": "application/json"}


def _require_hubspot() -> None:
    if not HUBSPOT_ACCESS_TOKEN:
        raise ValueError("Missing HubSpot config. Set HUBSPOT_ACCESS_TOKEN.")


@tool
def search_hubspot_company(company_name: str) -> dict:
    """Search HubSpot for a company by name.

    Returns company details including plan/tier, ARR, owner, and lifecycle stage.
    Useful for understanding customer context and importance.
    """
    _require_hubspot()
    url = "https://api.hubapi.com/crm/v3/objects/companies/search"
    payload = {
        "filterGroups": [{"filters": [{"propertyName": "name", "operator": "CONTAINS_TOKEN", "value": company_name}]}],
        "properties": ["name", "domain", "industry", "numberofemployees", "annualrevenue", "lifecyclestage",
                        "hs_lead_status", "hubspot_owner_id", "notes_last_contacted", "plan_tier",
                        "customer_tier", "contract_value", "subscription_type"],
        "limit": 5,
    }
    resp = requests.post(url, headers=_hubspot_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return {
        "count": len(results),
        "companies": [
            {
                "id": r["id"],
                "name": r["properties"].get("name"),
                "domain": r["properties"].get("domain"),
                "industry": r["properties"].get("industry"),
                "employees": r["properties"].get("numberofemployees"),
                "annual_revenue": r["properties"].get("annualrevenue"),
                "lifecycle_stage": r["properties"].get("lifecyclestage"),
                "plan_tier": r["properties"].get("plan_tier") or r["properties"].get("customer_tier") or r["properties"].get("subscription_type"),
                "contract_value": r["properties"].get("contract_value"),
                "last_contacted": r["properties"].get("notes_last_contacted"),
            }
            for r in results
        ],
    }


@tool
def get_hubspot_contact(email: str) -> dict:
    """Look up a HubSpot contact by email address.

    Returns contact details, associated company, deal info, and recent activity.
    """
    _require_hubspot()
    url = f"https://api.hubapi.com/crm/v3/objects/contacts/{email}"
    params = {
        "idProperty": "email",
        "properties": "firstname,lastname,email,company,jobtitle,lifecyclestage,hs_lead_status,notes_last_contacted,hubspot_owner_id",
        "associations": "companies,deals",
    }
    resp = requests.get(url, headers=_hubspot_headers(), params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    props = data.get("properties", {})

    associations = {}
    for assoc_type, assoc_data in data.get("associations", {}).items():
        associations[assoc_type] = [{"id": a["id"], "type": a.get("type")} for a in assoc_data.get("results", [])]

    return {
        "id": data.get("id"),
        "name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
        "email": props.get("email"),
        "company": props.get("company"),
        "job_title": props.get("jobtitle"),
        "lifecycle_stage": props.get("lifecyclestage"),
        "last_contacted": props.get("notes_last_contacted"),
        "associations": associations,
    }


# ---------------------------------------------------------------------------
# Notion tools (runbook search)
# ---------------------------------------------------------------------------

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_RUNBOOK_DB_ID = os.environ.get("NOTION_RUNBOOK_DB_ID", "")


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def _require_notion() -> None:
    if not NOTION_API_KEY:
        raise ValueError("Missing Notion config. Set NOTION_API_KEY.")


@tool
def search_notion_runbooks(query: str) -> dict:
    """Search Notion runbooks database for articles matching a query.

    Returns matching runbook titles, summaries, and page URLs.
    Use specific technical terms from the ticket for best results.
    """
    _require_notion()
    # Search the specific runbooks database
    url = f"https://api.notion.com/v1/databases/{NOTION_RUNBOOK_DB_ID}/query"
    payload: dict = {}
    if query:
        # Use Notion's filter for title property
        payload = {
            "filter": {
                "or": [
                    {"property": "title", "title": {"contains": query}},
                    {"property": "Name", "title": {"contains": query}},
                    {"property": "Tags", "multi_select": {"contains": query}},
                ]
            },
            "page_size": 10,
        }
    resp = requests.post(url, headers=_notion_headers(), json=payload, timeout=15)

    # Fallback to global search if database query fails
    if not resp.ok:
        search_url = "https://api.notion.com/v1/search"
        search_payload = {"query": query, "filter": {"value": "page", "property": "object"}, "page_size": 10}
        resp = requests.post(search_url, headers=_notion_headers(), json=search_payload, timeout=15)
        resp.raise_for_status()

    results = resp.json().get("results", [])
    pages = []
    for page in results:
        # Extract title from properties
        title = ""
        for prop_name, prop_val in page.get("properties", {}).items():
            if prop_val.get("type") == "title":
                title_parts = prop_val.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_parts)
                break

        pages.append({
            "id": page["id"],
            "title": title,
            "url": page.get("url", ""),
            "last_edited": page.get("last_edited_time"),
            "created": page.get("created_time"),
        })

    return {"count": len(pages), "runbooks": pages}


@tool
def get_notion_page_content(page_id: str) -> dict:
    """Retrieve the full content of a Notion page/runbook by its ID.

    Returns the page blocks as plain text for reading runbook instructions.
    """
    _require_notion()
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    params = {"page_size": 100}
    resp = requests.get(url, headers=_notion_headers(), params=params, timeout=15)
    resp.raise_for_status()
    blocks = resp.json().get("results", [])

    content_parts = []
    for block in blocks:
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})

        # Extract text from rich_text arrays
        if "rich_text" in block_data:
            text = "".join(rt.get("plain_text", "") for rt in block_data["rich_text"])
            if block_type.startswith("heading"):
                level = block_type[-1]  # heading_1 -> 1
                text = f"{'#' * int(level)} {text}"
            elif block_type == "bulleted_list_item":
                text = f"  - {text}"
            elif block_type == "numbered_list_item":
                text = f"  1. {text}"
            elif block_type == "to_do":
                checked = block_data.get("checked", False)
                text = f"  [{'x' if checked else ' '}] {text}"
            elif block_type == "code":
                lang = block_data.get("language", "")
                text = f"```{lang}\n{text}\n```"
            content_parts.append(text)
        elif block_type == "divider":
            content_parts.append("---")

    return {"page_id": page_id, "content": "\n".join(content_parts)[:5000]}


# ---------------------------------------------------------------------------
# GitHub tools (via gh CLI — requires `gh auth login`)
# ---------------------------------------------------------------------------

GITHUB_ORG = os.environ.get("GITHUB_ORG", "")


def _require_github() -> None:
    if not GITHUB_ORG:
        raise ValueError("Missing GitHub config. Set GITHUB_ORG.")


def _gh(*args: str, timeout: int = 30) -> str:
    """Run a gh CLI command and return stdout, or an error string."""
    _require_github()
    result = subprocess.run(
        ["gh", *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout


@tool
def search_github_issues(query: str, repo: str = "") -> str:
    """Search GitHub issues and pull requests for matching terms.

    Args:
        query: Search terms (e.g. "timeout error", "auth flow bug").
        repo: Optional repo in 'owner/repo' format. If empty, searches the whole org.

    Returns matching issues/PRs as JSON with number, title, state, labels, and URL.
    """
    search_q = f"{query} org:{GITHUB_ORG}" if not repo else query
    args = ["search", "issues", search_q, "--limit", "15",
            "--json", "number,title,state,url,labels,createdAt,updatedAt,body,repository"]
    if repo:
        if "/" in repo:
            args.extend(["--repo", repo])
        else:
            args.extend(["--repo", f"{GITHUB_ORG}/{repo}"])
    return _gh(*args)


@tool
def search_github_code(query: str, repo: str = "") -> str:
    """Search GitHub code across the organization's repositories.

    Args:
        query: Code search terms (e.g. 'def handle_webhook', 'class AuthMiddleware').
        repo: Optional repo name (e.g. 'backend') to narrow search.

    Returns matching files with path, repo, and match context.
    """
    search_q = query
    if repo:
        if "/" in repo:
            search_q += f" repo:{repo}"
        else:
            search_q += f" repo:{GITHUB_ORG}/{repo}"
    else:
        search_q += f" org:{GITHUB_ORG}"
    return _gh("search", "code", search_q, "--limit", "10",
               "--json", "path,repository,textMatches")


@tool
def get_github_releases(repo: str, limit: int = 5) -> str:
    """Get recent releases for a GitHub repository.

    Args:
        repo: Repository name (e.g. 'backend'). Will be prefixed with the org.
        limit: Number of releases to return (default 5).

    Returns release tags, names, dates, and release notes.
    """
    full_repo = repo if "/" in repo else f"{GITHUB_ORG}/{repo}"
    return _gh("release", "list", "--repo", full_repo, "--limit", str(limit),
               "--json", "tagName,name,publishedAt,body,isPrerelease,url")


@tool
def get_github_pull_request(repo: str, pr_number: int) -> str:
    """Get details of a specific GitHub pull request.

    Args:
        repo: Repository name (e.g. 'backend').
        pr_number: Pull request number.

    Returns PR title, description, status, review state, and changed files.
    """
    full_repo = repo if "/" in repo else f"{GITHUB_ORG}/{repo}"
    return _gh("pr", "view", str(pr_number), "--repo", full_repo,
               "--json", "number,title,state,url,body,createdAt,mergedAt,"
               "headRefName,baseRefName,changedFiles,files,reviews,merged")


@tool
def get_github_issue(repo: str, issue_number: int) -> str:
    """Get details of a specific GitHub issue.

    Args:
        repo: Repository name (e.g. 'backend').
        issue_number: Issue number.

    Returns issue title, body, labels, comments, and status.
    """
    full_repo = repo if "/" in repo else f"{GITHUB_ORG}/{repo}"
    return _gh("issue", "view", str(issue_number), "--repo", full_repo,
               "--json", "number,title,state,body,labels,comments,createdAt,updatedAt,url")


@tool
def list_github_prs(repo: str, state: str = "all", search: str = "", limit: int = 10) -> str:
    """List pull requests for a repository, optionally filtered by search terms.

    Args:
        repo: Repository name (e.g. 'backend').
        state: Filter by state — 'open', 'closed', 'merged', or 'all'.
        search: Optional search terms to filter PRs.
        limit: Maximum number of PRs to return (default 10).

    Returns PRs with number, title, state, author, and URL.
    """
    full_repo = repo if "/" in repo else f"{GITHUB_ORG}/{repo}"
    args = ["pr", "list", "--repo", full_repo, "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,url,createdAt,mergedAt,author,headRefName,labels"]
    if search:
        args.extend(["--search", search])
    return _gh(*args)


# ---------------------------------------------------------------------------
# PII guardrail — prevent leaking sensitive customer data in output
# ---------------------------------------------------------------------------

pii_guardrail = RegexGuardrail(
    patterns=[
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # credit card
        r"\b\d{3}-\d{2}-\d{4}\b",                          # SSN
    ],
    mode="block",
    position="output",
    on_fail="retry",
    message="Do not include credit card numbers or SSNs in the output. Redact any PII.",
)


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

# -- Specialist: Zendesk investigator --
zendesk_agent = Agent(
    name="zendesk_investigator",
    model=settings.llm_model,
    instructions="""\
You are a Zendesk specialist. Your job is to:
1. Fetch the given ticket and extract the core customer issue
2. Search for similar/related tickets to identify patterns (e.g. is this a recurring issue?)
3. Note the ticket's current status, priority, tags, and requester info

Return a structured summary covering:
- What the customer is experiencing (in their words and technical terms)
- Any error messages, screenshots, or logs mentioned
- How many other customers have reported similar issues
- The customer's email and organization for cross-referencing in other systems
""",
    tools=[get_zendesk_ticket, search_zendesk_tickets],
)

# -- Specialist: JIRA investigator --
jira_agent = Agent(
    name="jira_investigator",
    model=settings.llm_model,
    instructions="""\
You are a JIRA specialist. Given a description of a customer issue:
1. Search for related engineering tickets (bugs, feature requests, known issues)
2. Check if there's an existing fix in progress or already shipped
3. Look for related incidents or post-mortems

Use JQL queries like:
- text ~ "keyword" for full-text search
- labels = "customer-reported" for customer-facing issues
- status in ("In Progress", "In Review") for active work

Summarize what engineering knows about this issue and whether a fix exists.
""",
    tools=[search_jira_issues, get_jira_issue],
)

# -- Specialist: HubSpot investigator --
hubspot_agent = Agent(
    name="hubspot_investigator",
    model=settings.llm_model,
    instructions="""\
You are a HubSpot CRM specialist. Given a customer name or email:
1. Look up the company to understand their tier, plan, revenue, and importance
2. Look up the contact to see recent interactions and ownership

This context is critical for prioritization:
- Enterprise/high-revenue customers with production issues = higher priority
- Free tier users with feature requests = lower priority

Return the customer's plan tier, ARR/contract value, lifecycle stage, and account owner.
""",
    tools=[search_hubspot_company, get_hubspot_contact],
)

# -- Specialist: Notion runbook searcher --
runbook_agent = Agent(
    name="runbook_searcher",
    model=settings.llm_model,
    instructions="""\
You are a Notion runbook specialist. Given a technical issue description:
1. Search for runbooks that match the symptoms or error type
2. Read the most relevant runbook(s) to find step-by-step resolution instructions
3. Note any prerequisites, caveats, or escalation criteria from the runbooks

If you find a matching runbook, extract the key resolution steps.
If no runbook exists, say so — this is valuable info for the team (we need to create one).
""",
    tools=[search_notion_runbooks, get_notion_page_content],
)

# -- Specialist: GitHub code investigator --
github_agent = Agent(
    name="github_investigator",
    model=settings.llm_model,
    instructions="""\
You are a GitHub specialist using the gh CLI. Given a technical issue description:
1. Search for related issues and PRs (search_github_issues) that might contain fixes or discussions
2. Search the codebase for relevant code (search_github_code) — error messages, function names, config
3. Check recent releases (get_github_releases) to see if a fix was shipped or a regression was introduced
4. Drill into specific PRs (get_github_pull_request) or issues (get_github_issue) for full details
5. List recent PRs (list_github_prs) to spot recently merged changes that could be related

Focus on:
- Open issues with the same symptoms
- Recently merged PRs that might have introduced the bug
- Release notes mentioning relevant fixes
- Code paths that could be involved

Return relevant PRs, issues, code locations, and release versions.
All the source is in orkes-io/orkes-conductor and orkes-io/condutor-ui repositories
""",
    tools=[search_github_issues, search_github_code, get_github_releases,
           get_github_pull_request, get_github_issue, list_github_prs],
)


# -- Main orchestrator agent --
ORCHESTRATOR_INSTRUCTIONS = """\
You are a Customer Engineering Support Agent. Your job is to investigate a Zendesk \
support ticket by calling the investigator tools and relaying their findings.

WORKFLOW:
1. First, use the zendesk_investigator to fetch the ticket and find related tickets
2. In PARALLEL, use the other investigators to gather context:
   - hubspot_investigator: Look up the customer's tier and revenue (use the requester email or company name from the ticket)
   - jira_investigator: Search for related engineering issues using key terms from the ticket
   - runbook_searcher: Search for applicable runbooks using technical terms from the ticket
   - github_investigator: Search for related issues, PRs, and code using technical terms from the ticket
3. Compile ALL findings from every tool into your response

CRITICAL RULES:
- ONLY include information that was returned by the tools. Do NOT invent, assume, \
or hallucinate any details.
- If a tool returned no results or errored, state that explicitly \
(e.g. "JIRA: no related issues found", "Notion: no matching runbooks").
- Include the raw details: ticket IDs, JIRA keys, PR numbers, URLs, error messages, \
customer names, plan tiers — exactly as returned by the tools.
- Do NOT summarize away important details. Pass through everything the tools returned.
- Your response must contain the findings from ALL five investigators, clearly labeled.
"""

ce_investigator = Agent(
    name="ce_investigator",
    model=settings.llm_model,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=[
        agent_tool(zendesk_agent, description="Investigate the Zendesk ticket — fetch details and find related tickets"),
        agent_tool(hubspot_agent, description="Look up customer context in HubSpot — plan tier, revenue, importance"),
        agent_tool(jira_agent, description="Search JIRA for related engineering issues, bugs, and fixes"),
        agent_tool(runbook_agent, description="Search Notion runbooks for resolution procedures"),
        agent_tool(github_agent, description="Search GitHub for related issues, PRs, code, and releases"),
    ],
    guardrails=[pii_guardrail],
    max_turns=15,
    temperature=0.2,
)

# -- Report writer: synthesizes all findings into a markdown report --
REPORT_WRITER_INSTRUCTIONS = """\
You are a report writer for the Customer Engineering team. You receive the raw \
findings from multiple investigation agents (Zendesk, HubSpot, JIRA, Notion \
runbooks, and GitHub) and format them into a single, clear markdown report.

CRITICAL RULES:
- ONLY use information present in the input you received. Do NOT invent, guess, \
or assume ANY details that are not explicitly stated in the findings.
- If a section has no data from the findings, write "No data found." for that section.
- Include specific identifiers exactly as they appear: ticket IDs, JIRA keys, \
PR numbers, URLs, customer names, plan tiers, error messages, dates.
- Do NOT fabricate ticket numbers, JIRA keys, URLs, customer names, or any other specifics.
- Do NOT speculate about root causes or solutions unless the findings explicitly support them.

Your report MUST follow this structure:

# Ticket Investigation Report

## Ticket Overview
- Ticket ID, subject, status, and when it was created
- Customer name, email, company
- Customer tier/plan and contract value (from HubSpot findings)

## Priority Assessment
Use this guide to assign priority based ONLY on the facts in the findings:
- P0 (house on fire): Production down for enterprise customer, data loss, security breach
- P1 (critical): Major feature broken for high-tier customer, significant revenue impact
- P2 (high): Important feature degraded, workaround exists but painful, multiple customers affected
- P3 (medium): Non-critical issue, minor inconvenience, has workaround
- P4 (low): Enhancement request, cosmetic issue, documentation question

Priority modifiers (apply only if the findings contain evidence):
- Enterprise/high-revenue customer (from HubSpot) -> bump up 1 level
- Multiple customers reporting same issue (from Zendesk search) -> bump up 1 level
- Security-related -> minimum P1

State whether engineering escalation is needed based on the evidence.

## Customer Issue
- What the customer is experiencing (from Zendesk ticket description and comments)
- Key error messages or symptoms (quote them directly from the findings)
- Number of similar tickets found (from Zendesk search results)

## Root Cause Analysis
- Most likely root cause based ONLY on evidence from JIRA, GitHub, and runbook findings
- If no root cause can be determined from the findings, say so

## Recommended Solution
- Steps from matching runbooks (include runbook titles/links from Notion findings)
- Workarounds mentioned in JIRA or GitHub findings
- If no solution was found in the findings, say "No existing solution found — requires investigation"

## Related Issues
- JIRA tickets found (key, summary, status, assignee — from JIRA findings)
- GitHub issues and PRs found (number, title, state, URL — from GitHub findings)
- Similar Zendesk tickets found (ID, subject — from Zendesk search findings)
- If none found for a system, state "None found"

## Code References
- Files, PRs, commits, or releases from GitHub findings
- If none found, state "None found"

## Next Steps
- Numbered action items based on the findings
- If escalation is needed, state who/what team based on JIRA assignees or GitHub PR authors

Write in a professional, direct tone. Be specific. Never be vague.
"""

report_writer = Agent(
    name="report_writer",
    model=settings.llm_model,
    instructions=REPORT_WRITER_INSTRUCTIONS,
    guardrails=[pii_guardrail],
    temperature=0.3,
)

# -- Pipeline: investigate >> write report --
ce_support_agent = ce_investigator >> report_writer


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _get_result_text(output) -> str:
    """Extract the final text from an agent output."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        # Sequential pipeline wraps in {"result": "..."}
        result = output.get("result")
        if isinstance(result, str):
            return result
        return json.dumps(output, indent=2, default=str)
    return str(output)


def main():
    if len(sys.argv) < 2:
        print("Usage: python 70_ce_support_agent.py <ticket_id> [--stream]")
        print("Example: python 70_ce_support_agent.py 12345")
        sys.exit(1)

    ticket_id = sys.argv[1]
    use_stream = "--stream" in sys.argv

    prompt = f"Investigate Zendesk ticket #{ticket_id} and provide a full analysis with solution and priority."

    with AgentRuntime() as runtime:
        if use_stream:
            print(f"\n--- Investigating ticket #{ticket_id} (streaming) ---\n")
            for event in runtime.stream(ce_support_agent, prompt):
                if event.type == "tool_call":
                    print(f"  [{event.tool_name}] calling...")
                elif event.type == "tool_result":
                    print(f"  [{event.tool_name}] done")
                elif event.type == "handoff":
                    print(f"  -> handing off to {event.target}")
                elif event.type == "error":
                    print(f"  ERROR: {event.content}")
                elif event.type == "done":
                    print()
                    print(_get_result_text(event.output))
        else:
            print(f"\n--- Investigating ticket #{ticket_id} ---\n")
            result = runtime.run(ce_support_agent, prompt)
            print(_get_result_text(result.output))
            if result.token_usage:
                print(f"\n---\n*Tokens: {result.token_usage.total_tokens}*")


if __name__ == "__main__":
    main()
