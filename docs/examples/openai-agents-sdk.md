---
title: OpenAI Agents SDK — customer support
description: Multi-agent handoff system built with the OpenAI Agents SDK, wrapped with Agentspan
---

# OpenAI Agents SDK — Customer Support

This example shows how to wrap an existing OpenAI Agents SDK multi-agent system with Agentspan. A triage agent routes customer support tickets to billing, technical, or account specialists using the SDK's native handoff feature — with crash recovery and full handoff tracing added by changing one line.

## What Agentspan adds to the OpenAI Agents SDK

The OpenAI Agents SDK handles your agent definitions, handoffs, and tool routing. Agentspan adds a production execution layer without changing any of that:

- **Crash recovery**: If your process dies during a multi-step resolution, Agentspan resumes when a worker reconnects
- **Full handoff trace**: Every handoff between agents is a logged step, visible in the UI at `http://localhost:6767`
- **Human approval on tools**: Add `approval_required=True` to any tool to pause execution for human sign-off
- **Execution history**: Every ticket run is stored with inputs, outputs, and timing

Your agent definitions, handoff configurations, and tool implementations stay exactly as written.

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Additional dependencies: `pip install openai-agents`
    - Environment variables set:
    
    ```bash
    export OPENAI_API_KEY=sk-...
    ```

---

## Before: plain OpenAI Agents SDK

Standard code using the OpenAI Agents SDK. The native handoff pattern works well, but runs have no history, no crash recovery, and no human-in-the-loop.

```python
from agents import Agent, Runner, function_tool

# ── Mock data ─────────────────────────────────────────────────────────────────

ACCOUNTS = {
    "CUST-001": {"id": "CUST-001", "name": "Alice Smith", "plan": "pro", "billing_status": "active", "region": "us-east"},
}
INVOICES = {
    "INV-8821": {"id": "INV-8821", "customer_id": "CUST-001", "amount": 99.00, "status": "paid", "date": "2024-12-01"},
}
TICKETS = [
    {"id": "TKT-101", "customer_id": "CUST-001", "subject": "Login issue", "status": "resolved"},
]

# ── Tools ────────────────────────────────────────────────────────────────────

@function_tool
def get_account(customer_id: str) -> dict:
    """Look up a customer's account: plan, billing status, usage."""
    return ACCOUNTS.get(customer_id, {"error": "Account not found"})

@function_tool
def get_invoice(invoice_id: str) -> dict:
    """Fetch an invoice by ID."""
    return INVOICES.get(invoice_id, {"error": "Invoice not found"})

@function_tool
def process_refund(invoice_id: str, reason: str) -> dict:
    """Issue a full refund for an invoice."""
    invoice = INVOICES.get(invoice_id)
    if not invoice:
        return {"error": "Invoice not found"}
    return {"status": "refunded", "invoice_id": invoice_id, "amount": invoice["amount"]}

@function_tool
def get_ticket_history(customer_id: str) -> list[dict]:
    """Get the last 5 support tickets for a customer."""
    return [t for t in TICKETS if t["customer_id"] == customer_id][:5]

@function_tool
def reset_password(customer_id: str) -> dict:
    """Send a password reset email to the customer."""
    account = ACCOUNTS.get(customer_id)
    if not account:
        return {"error": "Account not found"}
    return {"status": "reset_email_sent", "customer_id": customer_id}

@function_tool
def check_service_status(region: str) -> dict:
    """Check current service health for a region."""
    return {"region": region, "status": "operational", "latency_ms": 42}

@function_tool
def escalate_to_human(ticket_id: str, reason: str, priority: str) -> dict:
    """Escalate this ticket to a human agent."""
    return {"status": "escalated", "ticket_id": ticket_id, "priority": priority, "eta_minutes": 15}

# ── Specialist agents ─────────────────────────────────────────────────────────

billing_agent = Agent(
    name="billing_specialist",
    model="gpt-4o",
    instructions="""You handle billing questions: invoices, charges, refunds, plan changes.
    Always look up the account first. Process refunds only for clear billing errors.
    For amounts over $200, escalate to a human.""",
    tools=[get_account, get_invoice, process_refund, escalate_to_human],
)

technical_agent = Agent(
    name="technical_specialist",
    model="gpt-4o",
    instructions="""You handle technical issues: login problems, service outages, API errors.
    Always check service status first. Reset passwords only after verifying the customer's identity.""",
    tools=[check_service_status, reset_password],
)

account_agent = Agent(
    name="account_specialist",
    model="gpt-4o",
    instructions="""You handle account changes: upgrades, downgrades, cancellations, data exports.
    Always look up ticket history before making changes. For cancellations, attempt retention first.""",
    tools=[get_ticket_history],
)

# ── Triage agent with handoffs ────────────────────────────────────────────────

triage_agent = Agent(
    name="support_triage",
    model="gpt-4o-mini",  # fast, cheap — just routes
    instructions="""You are a support triage agent. Understand the customer's issue
    and hand off to the right specialist immediately.

    - Billing, charges, invoices, refunds → billing_specialist
    - Login, outages, API errors, technical issues → technical_specialist
    - Plan changes, cancellations, account settings → account_specialist""",
    handoffs=[billing_agent, technical_agent, account_agent],
)

# ── Run (plain OpenAI Agents SDK — no durability) ─────────────────────────────

result = Runner.run_sync(
    triage_agent,
    "Hi, I was charged $99 twice last month (invoice INV-8821). Can I get a refund?",
)
print(result.final_output)
```

---

## After: wrapped with Agentspan

Replace `Runner.run_sync(triage_agent, message)` with `runtime.run(triage_agent, message)`. That's the only change. Agentspan auto-detects OpenAI Agents SDK agents — no extra imports or agent modifications needed.

```python
from agentspan.agents import AgentRuntime

message = "Hi, I was charged $99 twice last month (invoice INV-8821). Can I get a refund?"

# was: result = Runner.run_sync(triage_agent, message)
with AgentRuntime() as runtime:
    result = runtime.run(triage_agent, message)

print(result.output)
print(f"Run ID: {result.execution_id}")
```

`runtime.run()` registers the full multi-agent execution — including every handoff — as a single managed run on the Agentspan server.

---

## Run it

Save all the code above (tools, agents, and runtime block) into a single file called `support_bot.py`, then run:

```bash
python support_bot.py
```

---

## What this demonstrates

```
ticket → [support_triage] → handoff → [billing_specialist] → tools → final response
```

**Native handoffs, Agentspan runtime**: The triage agent, specialist agents, and handoff configuration stay exactly as written. Replace `Runner.run_sync` with `runtime.run` and the entire multi-agent execution runs on the Agentspan server.

**Full handoff trace**: Every handoff is a logged step. Open `http://localhost:6767` to see exactly which specialist handled the ticket, what tools they called, and what they returned.

**Crash recovery**: If your process dies during a complex multi-step billing resolution, Agentspan resumes when a worker reconnects. The customer's ticket isn't dropped.

**Run history**: Every execution is stored with inputs, outputs, token usage, and timing.

---

## Example modifications

### Run asynchronously

```python
import asyncio
from agentspan.agents import run_async

async def handle_ticket(message: str):
    result = await run_async(triage_agent, message)
    return result.output

asyncio.run(handle_ticket("I was charged twice last month"))
```

### Fire-and-forget for slow tickets

Use `start` to submit a ticket and return immediately without blocking.

```python
from agentspan.agents import start

handle = start(triage_agent, customer_message)
print(f"Ticket queued: {handle.execution_id}")

# Collect the result later
result = handle.stream().get_result()
print(result.output)
```

### Stream events as they happen

Use `stream` to process handoffs and tool calls in real time as the agents work through the ticket.

```python
from agentspan.agents import stream

for event in stream(triage_agent, customer_message):
    if event.type == "handoff":
        print(f"  → routed to {event.target}")
    elif event.type == "tool_call":
        print(f"  → {event.tool_name}({event.args})")
    elif event.type == "done":
        print(f"\n{event.output}")
```

---

## Adding human approval for large refunds

Wrap any sensitive tool with Agentspan's `@tool` decorator and set `approval_required=True`. Execution pauses at that tool call until a human approves or rejects it in the UI.

```python
from agentspan.agents import tool

@tool(approval_required=True)
def process_refund(invoice_id: str, reason: str) -> dict:
    """Issue a full refund. Requires human approval."""
    return billing_api.refund(invoice_id, reason=reason)

# Use it in your agent as normal
billing_agent = Agent(
    name="billing_specialist",
    tools=[get_account, get_invoice, process_refund, escalate_to_human],
    ...
)
```

---

## Testing

Use `mock_run` to test the multi-agent flow without a live server or real API calls. Supply the expected sequence of handoffs and tool calls; `mock_run` drives the agents through them and returns an `AgentResult` you can assert against.

```python
from agentspan.agents.testing import mock_run, MockEvent, expect

result = mock_run(
    triage_agent,
    "I was charged twice last month",
    events=[
        MockEvent.handoff("billing_specialist"),
        MockEvent.done("I've looked into your account. A refund has been initiated."),
    ]
)
expect(result).completed()
```
