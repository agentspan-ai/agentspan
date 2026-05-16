import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

"""Support Ticket Pipeline with Zendesk Integration

Same pipeline as 02, but the classifier fetches real tickets
from Zendesk instead of using hardcoded input.

Setup:
    pip install agentspan requests
    agentspan server start

    # Store credentials in the AgentSpan UI (localhost:6767 → Credentials):
    #   ZENDESK_API   = your Zendesk API token
    #   ZENDESK_EMAIL = your Zendesk email (e.g. you@company.com)

    python 02_support_ticket_zendesk.py
"""

import os
import requests
from agentspan.agents import Agent, AgentRuntime, tool


# ── Zendesk Tools ────────────────────────────────────────────────
# Credentials are injected into os.environ by the AgentSpan server
# at execution time. No secrets in code.

ZENDESK_SUBDOMAIN = "orkeshelp"


@tool(credentials=["ZENDESK_EMAIL", "ZENDESK_API"])
def get_ticket(ticket_id: int) -> dict:
    """Fetch a support ticket from Zendesk by ID."""
    auth = (f"{os.environ['ZENDESK_EMAIL']}/token", os.environ["ZENDESK_API"])
    resp = requests.get(
        f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}.json",
        auth=auth,
    )
    ticket = resp.json()["ticket"]
    return {
        "id": ticket["id"],
        "subject": ticket["subject"],
        "description": ticket["description"],
        "status": ticket["status"],
        "priority": ticket["priority"],
        "tags": ticket["tags"],
        "created_at": ticket["created_at"],
    }


@tool(credentials=["ZENDESK_EMAIL", "ZENDESK_API"])
def get_ticket_comments(ticket_id: int) -> list:
    """Fetch all comments/replies on a Zendesk ticket."""
    auth = (f"{os.environ['ZENDESK_EMAIL']}/token", os.environ["ZENDESK_API"])
    resp = requests.get(
        f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}/comments.json",
        auth=auth,
    )
    comments = resp.json()["comments"]
    return [
        {
            "author_id": c["author_id"],
            "body": c["plain_body"],
            "created_at": c["created_at"],
            "public": c["public"],
        }
        for c in comments
    ]


@tool(credentials=["ZENDESK_EMAIL", "ZENDESK_API"])
def search_recent_tickets(query: str) -> list:
    """Search Zendesk tickets. Use keywords like status, priority, or text."""
    auth = (f"{os.environ['ZENDESK_EMAIL']}/token", os.environ["ZENDESK_API"])
    resp = requests.get(
        f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/search.json",
        auth=auth,
        params={"query": f"type:ticket {query}", "per_page": 5},
    )
    results = resp.json().get("results", [])
    return [
        {
            "id": r["id"],
            "subject": r["subject"],
            "status": r["status"],
            "priority": r["priority"],
            "created_at": r["created_at"],
        }
        for r in results
    ]


@tool(credentials=["ZENDESK_EMAIL", "ZENDESK_API"])
def reply_to_ticket(ticket_id: int, message: str) -> dict:
    """Post a public comment on a Zendesk ticket. The customer will see this."""
    auth = (f"{os.environ['ZENDESK_EMAIL']}/token", os.environ["ZENDESK_API"])
    resp = requests.put(
        f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}.json",
        auth=auth,
        json={"ticket": {"comment": {"body": message, "public": True}}},
    )
    return {"status": "posted", "ticket_id": ticket_id}


@tool(credentials=["ZENDESK_EMAIL", "ZENDESK_API"])
def add_internal_note(ticket_id: int, note: str) -> dict:
    """Add a private internal note on a Zendesk ticket. Only your team sees this."""
    auth = (f"{os.environ['ZENDESK_EMAIL']}/token", os.environ["ZENDESK_API"])
    resp = requests.put(
        f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}.json",
        auth=auth,
        json={"ticket": {"comment": {"body": note, "public": False}}},
    )
    return {"status": "noted", "ticket_id": ticket_id}


# ── Agents ────────────────────────────────────────────────────────

classifier = Agent(
    name="classifier",
    model="openai/gpt-4o",
    instructions=(
        "You are a support ticket classifier. Fetch the ticket from "
        "Zendesk, read it, and produce a structured classification:\n"
        "- Customer: name and company (from the ticket)\n"
        "- Priority: P0 (outage), P1 (critical), P2 (degraded), P3 (minor)\n"
        "- Category: performance, bug, feature-request, billing, onboarding\n"
        "- Product area: which part of the product is affected\n"
        "- Customer sentiment: frustrated, neutral, positive\n"
        "- Key facts: bullet list of the specific issues mentioned\n\n"
        "Be concise and structured. Do not guess — only classify based "
        "on what the customer actually wrote.\n"
        "IMPORTANT: Always include the Zendesk ticket_id in your output."
    ),
    tools=[get_ticket, get_ticket_comments, search_recent_tickets],
)

responder = Agent(
    name="responder",
    model="openai/gpt-4o",
    instructions=(
        "You are a senior support engineer. Your job is simple:\n"
        "1. Read the classification from the previous agent.\n"
        "2. Draft a professional reply under 200 words that acknowledges "
        "the issue, confirms the problem, asks follow-up questions, and "
        "sets expectations for next steps.\n"
        "3. Call the reply_to_ticket tool NOW with ticket_id=7221 and "
        "your drafted message. Do not just say you posted — actually "
        "call the tool.\n\n"
        "Always call the tool. Never skip it."
    ),
    tools=[reply_to_ticket],
)

escalation_checker = Agent(
    name="escalation_checker",
    model="openai/gpt-4o",
    instructions=(
        "You are a support team lead. Your job is simple:\n"
        "1. Read the classification and response from the previous agents.\n"
        "2. This is a P1 enterprise customer issue. It MUST be escalated.\n"
        "3. Call the add_internal_note tool NOW with ticket_id=7221 and "
        "a note containing: customer name (from the classification — do NOT "
        "make up a name), impact summary, urgency, and what engineering "
        "should investigate.\n\n"
        "Always call the tool. Never skip it."
    ),
    tools=[add_internal_note],
)

# ── Pipeline ──────────────────────────────────────────────────────

pipeline = classifier >> responder >> escalation_checker


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("Starting support ticket pipeline (Zendesk)...\n")
        TICKET_ID = 7221
        result = runtime.run(
            pipeline,
            f"Triage Zendesk ticket #{TICKET_ID}. Use ticket_id={TICKET_ID} for all Zendesk tool calls.",
        )
        result.print_result()
