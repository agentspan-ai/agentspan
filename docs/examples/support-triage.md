---
title: Support ticket triage
description: Classify, auto-resolve, or escalate with human approval — plus full history per ticket
---

# Build a Support Triage Agent

Use this example to build an AI support agent that classifies incoming tickets, resolves simple issues automatically, and routes sensitive operations (refunds, credits, suspensions) through a human approval queue before executing.

## How it works

A single agent handles each ticket end-to-end:

1. Looks up the customer's account and ticket history
2. Diagnoses the issue
3. Resolves general and technical questions immediately via `send_reply`
4. Pauses for human review before executing billing or account actions
5. Returns a structured `Resolution` with what happened

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Environment variables set:
    
    ```bash
    export AGENTSPAN_SERVER_URL=http://localhost:6767/api
    export OPENAI_API_KEY=<YOUR-KEY>
    export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
    ```

## Full code

```python
from agentspan.agents import Agent, AgentHandle, AgentRuntime, tool, start
from pydantic import BaseModel
from enum import Enum

# ── Data types ────────────────────────────────────────────────────────────────

class TicketCategory(str, Enum):
    BILLING   = "billing"
    TECHNICAL = "technical"
    ACCOUNT   = "account"
    GENERAL   = "general"

class Resolution(BaseModel):
    category: TicketCategory
    action_taken: str
    response_to_customer: str
    requires_followup: bool

# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def lookup_customer(email: str) -> dict:
    """Fetch customer record: plan, billing status, open tickets, account age."""
    return {"id": "cust_123", "email": email, "plan": "pro", "billing_status": "active"}

@tool
def lookup_ticket_history(customer_id: str) -> list[dict]:
    """Fetch the last 10 support tickets for this customer."""
    return [{"id": "TKT-001", "subject": "Login issue", "status": "resolved"}]

@tool
def send_reply(customer_id: str, message: str) -> dict:
    """Send a reply to the customer and mark the ticket as resolved."""
    return {"status": "sent", "customer_id": customer_id}

@tool(approval_required=True)
def issue_refund(customer_id: str, amount_usd: float, reason: str) -> dict:
    """Issue a refund to the customer. Requires human approval."""
    return {"status": "refund_issued", "amount": amount_usd}

@tool(approval_required=True)
def suspend_account(customer_id: str, reason: str) -> dict:
    """Suspend a customer account. Requires human approval."""
    return {"status": "suspended", "customer_id": customer_id}

@tool(approval_required=True)
def apply_credit(customer_id: str, amount_usd: float, note: str) -> dict:
    """Apply account credit. Requires human approval."""
    return {"status": "credit_applied", "amount": amount_usd}

# ── Agent ─────────────────────────────────────────────────────────────────────

support_agent = Agent(
    name="support_agent",
    model="openai/gpt-4o-mini",
    output_type=Resolution,
    tools=[
        lookup_customer,
        lookup_ticket_history,
        send_reply,
        issue_refund,
        suspend_account,
        apply_credit,
    ],
    instructions="""You are a support agent for a SaaS product.

When a ticket arrives:
1. Look up the customer's account and ticket history.
2. Diagnose the issue based on context.
3. For general and technical questions: resolve directly with send_reply.
4. For billing actions (refunds, credits): use the appropriate tool — these will pause
   for human review before executing.
5. Return a Resolution with what happened.

Always be clear and empathetic in your response_to_customer.
Never invent facts about the customer's account.""",
)

# ── Ticket handler ────────────────────────────────────────────────────────────

def handle_ticket(ticket_id: str, customer_email: str, message: str, runtime: AgentRuntime):
    prompt = f"""
Ticket ID: {ticket_id}
Customer email: {customer_email}
Message: {message}
"""
    handle = start(support_agent, prompt, runtime=runtime)

    for event in handle.stream():
        if event.type == "waiting":
            print(f"Paused for approval — tool: {event.tool_name}, args: {event.args}")
            return handle.execution_id

    # No approval gate hit — already complete
    return None

# ── Approve or reject ─────────────────────────────────────────────────────────

def reviewer_approve(execution_id: str, runtime: AgentRuntime):
    handle = AgentHandle(execution_id=execution_id, runtime=runtime)
    handle.approve()

def reviewer_reject(execution_id: str, runtime: AgentRuntime, reason: str):
    handle = AgentHandle(execution_id=execution_id, runtime=runtime)
    handle.reject(reason)

# ── Run ───────────────────────────────────────────────────────────────────────

with AgentRuntime() as runtime:
    eid = handle_ticket(
        "TKT-002", "user@example.com", "I was charged twice. Please refund.", runtime
    )

    if eid:
        decision = input("\nApprove? (y/n): ").strip().lower()
        handle = AgentHandle(execution_id=eid, runtime=runtime)
        if decision == "y":
            handle.approve()
        else:
            reason = input("Rejection reason: ").strip()
            handle.reject(reason)

        print("\nWaiting for agent to complete...")
        result = handle.stream().get_result()
        result.print_result()
```

## Run it

Save the file as `support_triage.py`, and run it:

```bash
python support_triage.py
```

When the terminal prompts for human approval, approve or reject.

## What this demonstrates

**Human-in-the-loop (`approval_required=True`)**: When the agent calls a gated tool, execution pauses server-side indefinitely. The workflow holds its full state until a reviewer approves or rejects.

**Reconnect from any process**: `AgentHandle(execution_id=..., runtime=...)` lets you re-attach to a paused workflow from a completely different process (e.g. a webhook handler), without the original caller staying alive.

**Structured output**: `output_type=Resolution` enforces a typed response. The agent cannot return a free-form string; the SDK validates the output matches the schema.

**Risk-tiered tools**: `send_reply` executes immediately; `issue_refund`, `apply_credit`, and `suspend_account` always pause for human review before touching money or account state.

## Example modifications

### Approve from the CLI

If the agent is paused and you have the execution ID, you can approve or reject directly from the terminal without writing any code:

```bash
# Approve
agentspan agent respond <execution-id> --approve

# Reject
agentspan agent respond <execution-id> --reject --reason "Amount too large"
```

### Auto-approve low-risk actions

Route only high-value operations to a human reviewer, and approve the rest automatically:

```python
def reviewer_approve_or_escalate(execution_id: str, runtime: AgentRuntime, args: dict):
    if args and args.get("amount_usd", 999) <= 25:
        reviewer_approve(execution_id, runtime)
    else:
        notify_human(execution_id, args)
```

### Wire up a webhook approver

Store the `execution_id` from `handle_ticket` in your database, then approve or reject from a webhook when a reviewer clicks a button in your UI:

```python
@app.post("/approvals/{execution_id}/approve")
def approve(execution_id: str):
    reviewer_approve(execution_id, runtime)
    return {"status": "approved"}

@app.post("/approvals/{execution_id}/reject")
def reject(execution_id: str, reason: str):
    reviewer_reject(execution_id, runtime, reason)
    return {"status": "rejected"}
```
