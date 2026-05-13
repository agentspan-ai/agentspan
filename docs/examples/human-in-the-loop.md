---
title: Human-in-the-loop
description: Pause agents at risky steps, hold state indefinitely, and resume after human approval
---

# Human-in-the-loop

Agents are great at finding the right action. Humans are better at authorizing risky ones. Agentspan lets you pause an agent at any tool call, hold state indefinitely on the server (no timeouts, no data loss), and resume after a human approves or rejects.

---

## The one-line change

Add `approval_required=True` to any `@tool` decorator. That's it.

```python
from agentspan.agents import tool

@tool(approval_required=True)
def process_refund(order_id: str, amount: float) -> dict:
    """Process a refund. Requires human approval before executing."""
    return billing_api.refund(order_id, amount)
```

When the LLM calls this tool, Agentspan automatically:
1. Pauses the agent workflow
2. Sets `handle.get_status().is_waiting = True`
3. Holds the full agent state on the server (no timeout)
4. Waits for `handle.approve()` or `handle.reject(reason)`

---

## Complete example: refund agent

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Environment variables set:
    
    ```bash
    export OPENAI_API_KEY=sk-...   # or ANTHROPIC_API_KEY if using Anthropic
    ```

```python
import time
from agentspan.agents import Agent, tool, start

# Tools that run automatically
@tool
def get_order(order_id: str) -> dict:
    """Look up an order by ID."""
    return {"order_id": order_id, "amount": 29.99, "status": "delivered"}

@tool
def get_customer(customer_id: str) -> dict:
    """Get customer account details."""
    return {"customer_id": customer_id, "name": "Alex", "email": "alex@example.com"}

# Tool that requires human approval before executing
@tool(approval_required=True)
def process_refund(order_id: str, amount: float) -> dict:
    """Issue a refund. Requires human approval."""
    return {"refunded": True, "order_id": order_id, "amount": amount}

agent = Agent(
    name="refund_agent",
    model="openai/gpt-4o-mini",
    tools=[get_order, get_customer, process_refund],
    instructions="""You handle refund requests.
    1. Look up the order
    2. Look up the customer
    3. Call process_refund — it will pause for human approval automatically
    """,
)

# Start the agent — returns immediately, workflow runs on the server
handle = start(agent, "Customer Alex (cust_001) wants a refund on order ORD-8821")
print(f"Run ID: {handle.execution_id}")

# Poll until the agent reaches the approval checkpoint
for _ in range(60):
    time.sleep(2)
    status = handle.get_status()

    if status.is_waiting:
        print("\n--- Approval required ---")
        print(f"Agent wants to call: process_refund")
        print(f"Order: ORD-8821  Amount: $29.99")

        decision = input("Approve? (y/n): ").strip().lower()
        if decision == "y":
            handle.approve()
            print("Approved. Waiting for agent to complete...")
            result = handle.stream().get_result()
            print("\nResult:", result.output["result"])
        else:
            reason = input("Rejection reason: ").strip()
            handle.reject(reason)
            print("Rejected.")
        break

    if status.is_complete:
        print("Completed:", status.output["result"])
        break
```

When it reaches human review, the terminal prompts like this:

```bash
--- Approval required ---
Agent wants to call: process_refund
Order: ORD-8821  Amount: $29.99
```

After `approve()`, the agent executes `process_refund` and continues normally.

After `reject(reason)`, the agent receives the rejection in its context and can respond — for example, by escalating to a human queue or explaining the rejection to the user.

---

## Connecting a webhook or Slack approval

In production, you don't poll in a loop — you store the execution ID and trigger approval from a webhook or approval UI:

```python
# When a run starts, store the execution_id
handle = start(agent, customer_message)
db.store_pending_approval(
    execution_id=handle.execution_id,
    context={"customer": customer_id, "action": "refund"},
)
# Notify your approval channel (Slack, email, internal tool)
notify_approver(handle.execution_id)
```

```python
# Later — your approval endpoint (FastAPI, Flask, Lambda, etc.)
from agentspan.agents import AgentRuntime, AgentHandle

# In a web app, the agent (with its tools) must already be served.
# Call runtime.serve(agent, blocking=False) at app startup, then reconnect here.

@app.post("/approvals/{execution_id}/approve")
def approve(execution_id: str):
    handle = AgentHandle(execution_id=execution_id, runtime=app.state.runtime)
    handle.approve()
    return {"approved": True}

@app.post("/approvals/{execution_id}/reject")
def reject(execution_id: str, reason: str):
    handle = AgentHandle(execution_id=execution_id, runtime=app.state.runtime)
    handle.reject(reason)
    return {"rejected": True}
```

---

## Multiple approval points in one run

You can have multiple `approval_required` tools — each one creates a separate approval checkpoint:

```python
@tool(approval_required=True)
def send_email_blast(template_id: str, recipient_count: int) -> dict:
    """Send a marketing email to all subscribers. Requires approval."""
    return email_service.send(template_id, recipient_count)

@tool(approval_required=True)
def delete_account(customer_id: str, reason: str) -> dict:
    """Permanently delete a customer account. Requires approval."""
    return accounts_db.delete(customer_id)
```

Each time the agent calls one of these tools, it pauses and waits for a fresh `handle.approve()` before continuing.

---

## Stream events including approval pauses

```python
from agentspan.agents import stream

agent_stream = stream(agent, customer_message)
for event in agent_stream:
    if event.type == "tool_call":
        print(f"→ calling {event.tool_name}")
    elif event.type == "waiting":
        print("paused — waiting for approval")
        # In a real app: send notification, store execution_id, return
        agent_stream.approve()  # or agent_stream.reject("reason")
    elif event.type == "done":
        print(event.output["result"])  # output is a dict: {"result": "...", "finishReason": "STOP", ...}
        break
```

---

## Testing HITL flows

`MockEvent.waiting()` simulates the approval pause, then `MockEvent.done()` simulates the post-approval response:

```python
from agentspan.agents.testing import mock_run, MockEvent, expect

result = mock_run(
    agent,
    "Refund order ORD-8821",
    events=[
        MockEvent.tool_call("get_order", {"order_id": "ORD-8821"}),
        MockEvent.tool_result("get_order", {"amount": 29.99}),
        MockEvent.tool_call("process_refund", {"order_id": "ORD-8821", "amount": 29.99}),
        MockEvent.waiting("Waiting for refund approval"),
        MockEvent.done("Refund of $29.99 for order ORD-8821 has been processed."),
    ]
)

expect(result).completed().used_tool("process_refund")
```
