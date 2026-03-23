# Human-in-the-Loop (HITL)

Human-in-the-Loop lets agents pause execution and wait for human input before proceeding. Unlike in-memory agent frameworks where a pause means a blocked process, Conductor Agents pauses at the **workflow level** — the process can exit, restart, or scale to zero, and the workflow resumes exactly where it left off when the human responds. A tool approval can wait minutes, hours, or days.

## How It Works

### Architecture

```
Agent loop (DoWhile)
  ├── LLM call
  ├── Dispatch worker (routes the LLM output)
  └── SwitchTask on tool_type
        ├── "worker"   → execute tool → SetVariable(messages)
        ├── "http"     → HttpTask → merge result → SetVariable
        ├── "mcp"      → CallMcpTool → merge result → SetVariable
        └── "approval" → HumanTask → process_human_response worker → SetVariable
```

When a tool is marked `approval_required=True`, the dispatch worker detects this and returns `tool_type: "approval"` instead of executing the tool. The outer SwitchTask routes to the **approval branch**, which:

1. **HumanTask** — pauses the workflow. Conductor marks the workflow as `IN_PROGRESS` with the current task waiting for external input. The HumanTask receives the tool name and parameters so reviewers know what they're approving.

2. **Process human response worker** — a single worker that handles **any** response from the human:
   - `{"approved": True}` — executes the tool, appends the result to the conversation
   - `{"approved": False, "reason": "..."}` — appends a rejection message so the LLM can respond
   - Anything else (feedback, edits, arbitrary dict) — serialized as a user message for the LLM to process

3. **SetVariableTask** — writes the updated messages back to the workflow variables so the next LLM iteration sees the result.

### No Inner Branching

The worker handles all branching internally. There is no inner SwitchTask — this keeps the compiled workflow simple, avoids Conductor expression evaluation issues in nested contexts, and allows arbitrary human responses beyond approve/reject.

## API Reference

### Marking Tools for Approval

```python
from agentspan.agents import tool

@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer funds between accounts. Requires human approval."""
    return {"status": "completed", "from": from_acct, "to": to_acct, "amount": amount}
```

Any tool decorated with `approval_required=True` will pause the workflow for human review whenever the LLM decides to call it. Tools without this flag execute immediately.

### Starting an Agent (Async)

HITL requires the async `start()` API since the workflow pauses and you need to interact with it while it's running:

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="banker", model="openai/gpt-4o", tools=[transfer_funds])

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Transfer $500 from checking to savings")
    # handle.workflow_id is available immediately
```

### Checking Status

```python
status = handle.get_status()

status.is_waiting     # True when paused at a HumanTask
status.is_running     # True when actively executing
status.is_complete    # True when workflow finished
status.pending_tool   # {"tool_name": "transfer_funds", "parameters": {...}}
status.output         # Final output (when is_complete=True)
```

### Responding to the Human Task

**Approve** — execute the pending tool:
```python
handle.approve()
```

**Reject** — skip the tool with an optional reason:
```python
handle.reject("Amount exceeds daily limit")
```

**Send arbitrary response** — any dict the LLM can process:
```python
handle.respond({"approved": True})                          # same as approve()
handle.respond({"approved": False, "reason": "too risky"})  # same as reject()
handle.respond({"feedback": "Use metric units instead"})    # custom feedback
handle.respond({"edited_params": {"amount": 250}})          # modified parameters
```

**Send a message** — convenience for string messages:
```python
handle.send("Please also include the transaction fee")
```

### Using AgentRuntime Directly

All `AgentHandle` methods delegate to `AgentRuntime`, which can be called directly if you have the workflow ID (e.g., from a different process):

```python
runtime.respond(workflow_id, {"approved": True})
runtime.approve(workflow_id)
runtime.reject(workflow_id, reason="Denied by compliance")
runtime.send_message(workflow_id, "Add a note to the transfer")
```

## Examples

| Example | Description |
|---|---|
| [`09_human_in_the_loop.py`](../examples/09_human_in_the_loop.py) | Basic approval workflow — approve/reject a fund transfer |
| [`09b_hitl_with_feedback.py`](../examples/09b_hitl_with_feedback.py) | Custom feedback — human sends free-form input back to the LLM |
| [`09c_hitl_streaming.py`](../examples/09c_hitl_streaming.py) | Streaming + HITL — real-time events with an approval pause |

## Patterns

### Poll-and-Respond

The simplest pattern. Start the agent, poll for status, respond when waiting:

```python
handle = runtime.start(agent, prompt)

while True:
    status = handle.get_status()
    if status.is_waiting and status.pending_tool:
        print(f"Tool: {status.pending_tool['tool_name']}")
        handle.approve()  # or reject(), respond(), send()
    if status.is_complete:
        print(status.output)
        break
    time.sleep(1)
```

### Webhook / External System

Since the workflow persists in Conductor, you can respond from any process. Store the `workflow_id`, then respond later from a web server, Slack bot, or CI pipeline:

```python
# Process A: start the agent
handle = runtime.start(agent, prompt)
save_to_db(handle.workflow_id)  # persist the workflow ID

# Process B (hours later): respond
workflow_id = load_from_db()
runtime.approve(workflow_id)
```

### Multiple Approval Tools

Mix approved and non-approved tools freely. Only tools with `approval_required=True` pause the workflow:

```python
@tool
def check_balance(account_id: str) -> dict:
    """Check balance — no approval needed."""
    return {"balance": 15000.00}

@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer funds — requires approval."""
    return {"status": "completed", "amount": amount}

@tool(approval_required=True)
def close_account(account_id: str) -> dict:
    """Close an account — requires approval."""
    return {"status": "closed", "account_id": account_id}

agent = Agent(
    name="banker",
    model="openai/gpt-4o",
    tools=[check_balance, transfer_funds, close_account],
)
```

The agent can call `check_balance` freely. If the LLM calls `transfer_funds` or `close_account`, the workflow pauses for approval each time.

### Custom Human Response

The `respond()` method accepts any dict. The worker serializes non-standard responses as user messages for the LLM:

```python
# Human provides feedback instead of approve/reject
handle.respond({"feedback": "Change the destination account to ACC-999"})

# The LLM sees this as a user message and can adjust its next action
```

This enables use cases beyond binary approve/reject: editorial feedback, parameter corrections, clarification questions, and multi-step human-agent collaboration.
