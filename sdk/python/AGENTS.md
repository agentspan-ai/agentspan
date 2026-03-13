# Conductor Agents SDK — API Reference & Architecture

Complete reference for the `agentspan.agents` Python SDK.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Agent](#agent)
- [Tools](#tools)
- [Execution API](#execution-api)
- [Result Types](#result-types)
- [Human-in-the-Loop](#human-in-the-loop)
- [Guardrails](#guardrails)
- [Structured Output](#structured-output)
- [Memory](#memory)
- [Multi-Agent Strategies](#multi-agent-strategies)
- [Architecture](#architecture)
- [Configuration](#configuration)

---

## Core Concepts

### Everything is an Agent

There is one orchestration primitive: `Agent`. A single agent wraps an LLM + tools. An agent with sub-agents IS a multi-agent system. No separate Team, Network, or Swarm classes.

### Server-First Execution

Unlike other agent SDKs that run everything in-process, Conductor Agents compiles agents into **durable Conductor workflows**. Tools execute as distributed Conductor tasks. The agent survives process crashes, tools scale independently, and human approvals can take days.

### Design
Design docs can be found in [docs/](docs/) folder
### The Compilation Model

```
Agent(Python)  →  compile  →  ConductorWorkflow(JSON)  →  execute
```

When you call `run(agent, "message")`, the SDK:
1. Compiles the Agent into a Conductor workflow definition (with inline workflow def)
2. Starts worker processes for `@tool` functions
3. Executes the workflow
4. Returns the result

---

## Agent

```python
from agentspan.agents import Agent
```

The single orchestration primitive.

### Constructor

```python
Agent(
    name: str,                                      # Unique name (becomes workflow name)
    model: str,                                      # "provider/model" format
    instructions: Union[str, Callable] = "",          # System prompt
    tools: Optional[List] = None,                    # @tool functions or ToolDef
    agents: Optional[List[Agent]] = None,            # Sub-agents
    strategy: str = "handoff",                       # Multi-agent strategy
    router: Optional[Union[Agent, Callable]] = None, # For "router" strategy
    output_type: Optional[type] = None,              # Pydantic model for structured output
    guardrails: Optional[List[Guardrail]] = None,    # Input/output validation
    memory: Optional[ConversationMemory] = None,     # Session management
    dependencies: Optional[Dict[str, Any]] = None,   # Injected into ToolContext
    max_turns: int = 25,                             # Maximum agent loop iterations
    max_tokens: Optional[int] = None,                # LLM max tokens
    temperature: Optional[float] = None,             # LLM temperature
    stop_when: Optional[Callable] = None,            # Early termination condition
    metadata: Optional[Dict[str, Any]] = None,       # Arbitrary metadata
)
```

### Parameters

**`name`** — Unique identifier for the agent. Used as the Conductor workflow name.

**`model`** — LLM model in `"provider/model"` format. The provider must be configured as an AI integration in Conductor.

Examples: `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4-20250514"`, `"azure_openai/gpt-4o"`, `"google_gemini/gemini-pro"`, `"aws_bedrock/anthropic.claude-v2"`.

**`instructions`** — System prompt. Can be a string or a callable that returns a string (for dynamic prompts).

```python
# Static
Agent(name="bot", model="openai/gpt-4o", instructions="You are helpful.")

# Dynamic
Agent(name="bot", model="openai/gpt-4o",
      instructions=lambda: f"Today is {date.today()}. Be helpful.")
```

**`tools`** — List of `@tool`-decorated functions, `ToolDef` instances, or a mix. See [Tools](#tools).

**`agents`** — Sub-agents for multi-agent orchestration. See [Multi-Agent Strategies](#multi-agent-strategies).

**`strategy`** — How sub-agents are orchestrated (only relevant when `agents` is provided):
- `"handoff"` (default) — LLM chooses which sub-agent to delegate to
- `"sequential"` — Sub-agents run in order, output feeds forward
- `"parallel"` — All sub-agents run concurrently, results aggregated
- `"router"` — A router agent or function selects which sub-agent runs

**`output_type`** — A Pydantic `BaseModel` subclass. The LLM's response is validated and parsed into this type. See [Structured Output](#structured-output).

**`guardrails`** — List of `Guardrail` instances. See [Guardrails](#guardrails).

**`memory`** — Optional `ConversationMemory` for session management. Pre-populates conversation history and limits message window size. See [Memory](#memory).

```python
from agentspan.agents import Agent, ConversationMemory

memory = ConversationMemory(max_messages=50)
agent = Agent(name="bot", model="openai/gpt-4o", memory=memory)
```

**`dependencies`** — Dict of objects to inject into tools via `ToolContext`. Useful for DB connections, API clients, user identity. See [Tool Context](#tool-context).

```python
agent = Agent(
    name="bot", model="openai/gpt-4o",
    tools=[query_db],
    dependencies={"db": my_database, "user_id": "u-123"},
)
```

**`max_turns`** — Maximum iterations of the think-act-observe loop. Prevents runaway agents. Default 25.

**`stop_when`** — Optional callable `(context: dict) -> bool`. Evaluated after each tool call. If it returns `True`, the agent stops the loop early. The context dict contains `result`, `messages`, and `iteration`.

```python
def budget_check(ctx):
    return ctx["iteration"] >= 3  # Stop after 3 tool calls

agent = Agent(name="bot", model="openai/gpt-4o", tools=[...], stop_when=budget_check)
```

### Chaining Operator

The `>>` operator creates sequential pipelines:

```python
pipeline = researcher >> writer >> editor
# Equivalent to:
Agent(name="researcher_writer_editor",
      model=researcher.model,
      agents=[researcher, writer, editor],
      strategy="sequential")
```

---

## Tools

```python
from agentspan.agents import tool, ToolDef, ToolContext, http_tool, mcp_tool
```

### @tool Decorator

Register a Python function as an agent tool. The function becomes a Conductor task definition executed by a distributed worker.

```python
@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "Sunny"}
```

With options:

```python
@tool(name="custom_name", approval_required=True, timeout_seconds=60)
def dangerous_action(target: str) -> dict:
    """Do something that needs human approval."""
    return {"done": True}
```

**Parameters:**
- `name` — Override the tool name (default: function name)
- `approval_required` — Insert a `WaitTask` before execution for human approval
- `timeout_seconds` — Maximum execution time

**How it works:**
1. JSON Schema is generated from the function's type hints and docstring
2. The schema is registered as a Conductor task definition
3. The function is registered as a Conductor worker
4. When the LLM calls this tool, Conductor schedules it as a task
5. A worker picks it up, executes the function, returns the result

The decorated function still works as a normal Python function:

```python
@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

add(2, 3)  # -> 5 (works normally)
```

### ToolDef

A fully-resolved tool definition. Most users won't create these directly.

```python
ToolDef(
    name: str,                           # Tool name
    description: str = "",               # Description for the LLM
    input_schema: Dict = {},             # JSON Schema for inputs
    output_schema: Dict = {},            # JSON Schema for outputs
    func: Optional[Callable] = None,     # Python function (None for server-side)
    approval_required: bool = False,     # Requires human approval
    timeout_seconds: Optional[int] = None,
    tool_type: str = "worker",           # "worker", "http", or "mcp"
    config: Dict = {},                   # Extra config (URL, headers, etc.)
)
```

### http_tool()

Create a tool backed by an HTTP endpoint. Executes entirely server-side via Conductor's `HttpTask` — no worker process needed.

```python
weather_api = http_tool(
    name="get_weather",
    description="Get weather for a city",
    url="https://api.weather.com/v1/current",
    method="GET",
    headers={"Authorization": "Bearer token"},
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)
```

### mcp_tool()

Create tools from an MCP (Model Context Protocol) server. Tools are discovered at runtime. Executes server-side via Conductor's `ListMcpTools` + `CallMcpTool`.

```python
github = mcp_tool(
    server_url="http://localhost:8080/mcp",
    name="github",
    description="GitHub operations",
)
```

### Mixing Tool Types

Agents can use Python tools, HTTP tools, and MCP tools together:

```python
agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    tools=[get_weather, weather_api, github],  # Python + HTTP + MCP
)
```

### Tool Context

Tools can receive execution context via dependency injection. Declare a `context: ToolContext` parameter and it will be injected automatically. Tools without `context` work unchanged.

```python
from agentspan.agents import tool, ToolContext

@tool
def query_database(query: str, context: ToolContext) -> dict:
    """Run a database query with the user's permissions."""
    db = context.dependencies["db"]
    user_id = context.dependencies["user_id"]
    return db.execute(query, user=user_id)
```

`ToolContext` fields:

| Field | Type | Description |
|---|---|---|
| `session_id` | `str` | Session ID for the current execution |
| `workflow_id` | `str` | Conductor workflow ID |
| `agent_name` | `str` | Name of the executing agent |
| `metadata` | `Dict` | Metadata from the agent |
| `dependencies` | `Dict` | User-provided dependencies |

The `context` parameter is excluded from the tool's JSON Schema (the LLM never sees it).

### Circuit Breaker

Tools that fail 3 consecutive times are automatically disabled. The LLM is told to use a different approach. On a successful call, the error counter resets.

### Robust Parsing

The dispatch worker handles common LLM output issues:
- Markdown code fences (`` ```json ... ``` ``) are stripped
- JSON embedded in explanatory text is extracted
- Variant key names are normalized (`"tool"` -> `"function"`, `"params"` -> `"function_parameters"`)

---

## Execution API

```python
from agentspan.agents import run, start, stream, run_async
```

### run() — Synchronous

Blocks until the agent completes. Simplest way to run an agent.

```python
result = run(agent, "What's the weather?")
result.output          # Final answer
result.workflow_id     # Conductor workflow ID
result.messages        # Conversation history
result.tool_calls      # Tool invocations
result.status          # "COMPLETED", "FAILED", etc.
```

**Parameters:**
- `agent` — The Agent to execute
- `prompt` — User's input message
- `session_id` — Optional session ID for multi-turn continuity
- `idempotency_key` — Optional key to prevent duplicate executions
- `runtime` — Optional custom `AgentRuntime` (default: shared singleton)

A shared singleton `AgentRuntime` is created on first use and reused across calls. Workers are long-lived and shut down at process exit. Pass a custom runtime for isolated configurations.

### start() — Fire-and-Forget

Returns immediately with a handle. For long-running or human-in-the-loop agents.

```python
handle = start(agent, "Analyze Q4 reports and get approval")
handle.workflow_id     # Track in Conductor UI

# Later, from any process, even after restarts:
status = handle.get_status()
if status.is_complete:
    print(status.output)
elif status.is_waiting:
    handle.approve()
```

### stream() — Real-Time Events

Yields events as the agent executes.

```python
for event in stream(agent, "Write a report"):
    match event.type:
        case "thinking":        print(event.content)
        case "tool_call":       print(f"Calling {event.tool_name}({event.args})")
        case "tool_result":     print(f"Result: {event.result}")
        case "handoff":         print(f"Delegating to {event.target}")
        case "waiting":         print("Waiting for approval...")
        case "guardrail_pass":  print(f"Guardrail passed: {event.guardrail_name}")
        case "guardrail_fail":  print(f"Guardrail failed: {event.guardrail_name}")
        case "done":            print(f"Final: {event.output}")
```

### run_async() — Async

Async counterpart of `run()`.

```python
result = await run_async(agent, "What's the weather?")
```

---

## Result Types

### AgentResult

Returned by `run()` and `run_async()`.

| Field | Type | Description |
|---|---|---|
| `output` | `Any` | Final answer (or typed Pydantic model if `output_type` set) |
| `workflow_id` | `str` | Conductor workflow ID |
| `correlation_id` | `Optional[str]` | Session/correlation ID |
| `messages` | `List[Dict]` | Full conversation history |
| `tool_calls` | `List[Dict]` | All tool invocations with inputs/outputs |
| `status` | `str` | `"COMPLETED"`, `"FAILED"`, etc. |
| `token_usage` | `Optional[TokenUsage]` | Aggregated token usage across all LLM calls |
| `metadata` | `Dict` | Extra workflow metadata |

### AgentHandle

Returned by `start()`. A handle to a running workflow.

| Method | Description |
|---|---|
| `get_status()` | Fetch current status → `AgentStatus` |
| `approve()` | Approve a pending human-in-the-loop task |
| `reject(reason)` | Reject with reason |
| `send(message)` | Send a message to the agent (multi-turn) |
| `pause()` | Pause the workflow |
| `resume()` | Resume a paused workflow |
| `cancel(reason)` | Cancel the workflow |
| `workflow_id` | The Conductor workflow ID (attribute) |

### AgentStatus

Returned by `handle.get_status()`.

| Field | Type | Description |
|---|---|---|
| `workflow_id` | `str` | Conductor workflow ID |
| `is_complete` | `bool` | Reached terminal state |
| `is_running` | `bool` | Still executing |
| `is_waiting` | `bool` | Paused for human input |
| `output` | `Any` | Available when complete |
| `status` | `str` | Raw Conductor status |
| `current_task` | `Optional[str]` | Current task reference name |
| `messages` | `List[Dict]` | Messages so far |

### AgentEvent

Yielded by `stream()`.

| Field | Type | Description |
|---|---|---|
| `type` | `str` | Event type (see below) |
| `content` | `Optional[str]` | Text (thinking, message, error) |
| `tool_name` | `Optional[str]` | Tool name (tool_call, tool_result) |
| `args` | `Optional[Dict]` | Tool arguments (tool_call) |
| `result` | `Any` | Tool result (tool_result) |
| `target` | `Optional[str]` | Agent name (handoff) |
| `output` | `Any` | Final output (done) |
| `workflow_id` | `str` | Conductor workflow ID |
| `guardrail_name` | `Optional[str]` | Guardrail name (guardrail_pass, guardrail_fail) |

**Event types:** `thinking`, `tool_call`, `tool_result`, `handoff`, `waiting`, `message`, `error`, `done`, `guardrail_pass`, `guardrail_fail`

---

## Human-in-the-Loop

Tools with `approval_required=True` pause the workflow until a human approves or rejects.

```python
@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer funds. Requires human approval."""
    return bank_api.transfer(from_acct, to_acct, amount)

agent = Agent(name="banker", model="openai/gpt-4o", tools=[check_balance, transfer_funds])

handle = start(agent, "Transfer $5000 from checking to savings")
# Workflow pauses when transfer_funds is about to execute

# Hours or days later, from any process, any machine:
status = handle.get_status()
if status.is_waiting:
    handle.approve()
    # or: handle.reject("Amount exceeds daily limit")
```

**How it works:** `approval_required=True` inserts a Conductor `WaitTask` before the tool's worker task. The workflow pauses until the task is completed via the API. There is no timeout — the workflow waits indefinitely.

### Multi-Turn Conversations

Use `handle.send()` to continue a conversation with a running agent:

```python
handle = start(agent, "My name is Alice")
handle.send("What's my name?")       # -> "Your name is Alice"
handle.send("I like Python")
handle.send("What do I like?")       # -> "You like Python"
```

Sessions persist across process restarts via Conductor workflow state.

---

## Guardrails

```python
from agentspan.agents import (
    Guardrail, GuardrailResult, guardrail, GuardrailDef, OnFail, Position,
)
```

Guardrails validate agent input or output. On failure with `on_fail="retry"`, feedback is sent back to the LLM.

### Enums

```python
class OnFail(str, Enum):
    RETRY = "retry"    # Append feedback, re-run LLM
    RAISE = "raise"    # Fail the workflow immediately
    FIX   = "fix"      # Use guardrail's fixed_output
    HUMAN = "human"    # Pause for human review (HumanTask)
```

```python
class Position(str, Enum):
    INPUT  = "input"   # Before the LLM call
    OUTPUT = "output"  # After the LLM call
```

Both are `str` subclasses — plain strings (`"retry"`, `"output"`) still work everywhere.

### GuardrailResult

```python
GuardrailResult(
    passed: bool,                            # True if content passes
    message: str = "",                       # Feedback for the LLM on retry
    fixed_output: Optional[str] = None,      # Corrected output for on_fail="fix"
)
```

### `@guardrail` Decorator

```python
@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject responses containing PII."""
    ...

# With custom name:
@guardrail(name="pii_checker")
def no_pii(content: str) -> GuardrailResult:
    ...
```

The decorator attaches a `GuardrailDef` (parallel to `ToolDef`) and is detected automatically by the `Guardrail` constructor.

### Guardrail

```python
Guardrail(
    func: Optional[Callable[[str], GuardrailResult]] = None,  # Local validation function or @guardrail-decorated function
    position: Union[str, Position] = Position.OUTPUT,          # Position.INPUT or Position.OUTPUT
    on_fail: Union[str, OnFail] = OnFail.RETRY,                # OnFail.RETRY, .RAISE, .FIX, or .HUMAN
    name: Optional[str] = None,                                # Defaults to function name; required for external guardrails
    max_retries: int = 3,                                      # Max retries for OnFail.RETRY
)
```

**External guardrails** — reference a guardrail worker running in another service by name alone (no local function):

```python
Guardrail(name="compliance_checker", on_fail=OnFail.RETRY)
```

The `external` property is `True` when `func is None`.

**`position`:**
- `Position.INPUT` / `"input"` — Runs before the LLM call (validates user input)
- `Position.OUTPUT` / `"output"` — Runs after the LLM call (validates LLM response)

**`on_fail`:**
- `OnFail.RETRY` / `"retry"` — Append the guardrail's message to the conversation and call the LLM again
- `OnFail.RAISE` / `"raise"` — Fail the workflow immediately
- `OnFail.FIX` / `"fix"` — Use the guardrail's `fixed_output`
- `OnFail.HUMAN` / `"human"` — Pause for human review via Conductor HumanTask

### Example

```python
import re
from agentspan.agents import Agent, Guardrail, GuardrailResult, OnFail, Position, guardrail

@guardrail
def no_pii(content: str) -> GuardrailResult:
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", content):
        return GuardrailResult(passed=False, message="Contains PII. Remove it.")
    return GuardrailResult(passed=True)

@guardrail
def word_limit(content: str) -> GuardrailResult:
    if len(content.split()) > 500:
        return GuardrailResult(passed=False, message="Too long. Be concise.")
    return GuardrailResult(passed=True)

agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o",
    guardrails=[
        Guardrail(no_pii, position=Position.OUTPUT, on_fail=OnFail.RETRY),
        Guardrail(word_limit, position=Position.OUTPUT, on_fail=OnFail.RETRY),
    ],
)
```

### RegexGuardrail

Pattern-based validation using regular expressions. Compiles as an `InlineTask` (server-side JavaScript) — no Python worker needed.

```python
from agentspan.agents import RegexGuardrail

RegexGuardrail(
    patterns: Union[str, List[str]],                # Regex pattern(s) to match
    mode: str = "block",                             # "block" (reject matches) or "allow" (require matches)
    position: Union[str, Position] = Position.OUTPUT, # Position.INPUT or Position.OUTPUT
    on_fail: Union[str, OnFail] = OnFail.RETRY,       # OnFail.RETRY, .RAISE, or .FIX
    name: Optional[str] = None,                      # Guardrail name
    message: Optional[str] = None,                   # Custom failure message
    max_retries: int = 3,                            # Max retries for OnFail.RETRY
)
```

**Modes:**
- `"block"` (default) — Fail if **any** pattern matches the content (blocklist)
- `"allow"` — Fail if **no** pattern matches the content (allowlist)

```python
# Block email addresses
no_emails = RegexGuardrail(
    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
    name="no_emails",
    message="Do not include email addresses in the response.",
)

# Require JSON output
json_only = RegexGuardrail(
    patterns=[r"^\s*[\{\[]"],
    mode="allow",
    name="json_output",
    message="Response must be valid JSON.",
)
```

### LLMGuardrail

AI-powered content evaluation using a judge LLM. The LLM evaluates content against a policy and returns a pass/fail judgment.

```python
from agentspan.agents import LLMGuardrail

LLMGuardrail(
    model: str,                                      # "provider/model" format
    policy: str,                                     # What the guardrail should check for
    position: Union[str, Position] = Position.OUTPUT, # Position.INPUT or Position.OUTPUT
    on_fail: Union[str, OnFail] = OnFail.RETRY,       # OnFail.RETRY or .RAISE
    name: Optional[str] = None,                      # Guardrail name
    max_retries: int = 3,                            # Max retries for OnFail.RETRY
)
```

Requires `litellm` (`pip install litellm`).

```python
safety = LLMGuardrail(
    model="openai/gpt-4o-mini",
    policy="Reject content that contains harmful or discriminatory language.",
    name="safety_check",
    on_fail=OnFail.RAISE,
)

agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o",
    guardrails=[safety],
)
```

---

## Structured Output

Use `output_type` to get validated, typed responses:

```python
from pydantic import BaseModel

class WeatherReport(BaseModel):
    city: str
    temperature: float
    condition: str
    recommendation: str

agent = Agent(
    name="reporter",
    model="openai/gpt-4o",
    tools=[get_weather],
    output_type=WeatherReport,
)

result = run(agent, "What's the weather in NYC?")
report: WeatherReport = result.output
print(report.city)           # Typed access
print(report.temperature)    # Validated
```

The Pydantic model's JSON Schema is passed to `LlmChatComplete(output_schema=...)` for server-side structured output.

---

## Memory

```python
from agentspan.agents import ConversationMemory
```

Conversation state is persisted in Conductor workflow variables, surviving process crashes.

```python
ConversationMemory(
    messages: List[Dict] = [],       # Conversation messages
    max_messages: Optional[int],     # Max messages to retain (trims oldest)
    max_tokens: Optional[int],       # Token budget for conversation window
)
```

**Methods:**
- `add_user_message(content)` — Append user message
- `add_assistant_message(content)` — Append assistant message
- `add_system_message(content)` — Append system message
- `add_tool_call(tool_name, arguments)` — Record a tool call
- `add_tool_result(tool_name, result)` — Record a tool result
- `to_chat_messages()` — Get messages in ChatMessage-compatible format
- `clear()` — Clear all history

### Using Memory with Agent

Pass a `ConversationMemory` to seed conversation history and control the message window:

```python
from agentspan.agents import Agent, ConversationMemory, run

memory = ConversationMemory(max_messages=50)

# Pre-seed with context
memory.add_system_message("User prefers concise answers.")
memory.add_user_message("My name is Alice.")
memory.add_assistant_message("Hello Alice!")

agent = Agent(
    name="bot",
    model="openai/gpt-4o",
    memory=memory,
)

result = run(agent, "What's my name?")  # Agent remembers "Alice"
```

When `max_messages` is set, the dispatch worker trims the message history after each turn, keeping system messages and the most recent non-system messages.

---

## Multi-Agent Strategies

Everything is an Agent. An Agent with `agents=[...]` is a multi-agent system.

### Handoff (default)

The parent agent's LLM decides which sub-agent to delegate to. Sub-agents appear as callable tools.

```python
support = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions="Route requests to the right specialist.",
    agents=[billing_agent, technical_agent, sales_agent],
    strategy="handoff",
)
```

**Conductor mapping:** Sub-agents become `ToolSpec(type="SUB_WORKFLOW")`. Selection triggers an `InlineSubWorkflowTask`.

### Sequential

Sub-agents run in order. Output of agent N becomes input of agent N+1.

```python
pipeline = Agent(
    name="content_pipeline",
    model="openai/gpt-4o",
    agents=[researcher, writer, editor],
    strategy="sequential",
)
# Or equivalently:
pipeline = researcher >> writer >> editor
```

**Conductor mapping:** Chain of `SubWorkflowTask` calls.

### Parallel

All sub-agents run concurrently on the same input. Results are aggregated.

```python
analysis = Agent(
    name="analysis",
    model="openai/gpt-4o",
    agents=[market_analyst, risk_analyst, compliance_checker],
    strategy="parallel",
)
```

**Conductor mapping:** `ForkTask` + `JoinTask` for concurrent execution.

### Router

A router agent or function selects which sub-agent runs each turn.

**Agent-based router** — uses the router agent's model and instructions for the routing decision:

```python
router_agent = Agent(
    name="router",
    model="anthropic/claude-sonnet-4-20250514",  # Can use a different model
    instructions="Route based on request type.",
)

team = Agent(
    name="dev_team",
    model="openai/gpt-4o",
    agents=[planner, coder, reviewer],
    strategy="router",
    router=router_agent,
)
```

**Function-based router** — a Python function registered as a Conductor worker task:

```python
def route(prompt: str) -> str:
    if "code" in prompt.lower():
        return "coder"
    return "planner"

team = Agent(
    name="dev_team",
    model="openai/gpt-4o",
    agents=[planner, coder, reviewer],
    strategy="router",
    router=route,
)
```

**Conductor mapping:** Agent-based: Router `LlmChatComplete` -> `SwitchTask`. Function-based: Router worker task -> `SwitchTask`.

### Hybrid (Tools + Sub-Agents)

An agent can have both its own tools AND sub-agents. Sub-agents become virtual `transfer_to_{name}` tools. The agent uses its own tools for direct work and transfers to sub-agents when delegation is needed.

```python
@tool
def search(query: str) -> str:
    """Search the web."""
    return f"Results for {query}"

specialist = Agent(name="specialist", model="openai/gpt-4o",
                   instructions="Deep domain expert.")

coordinator = Agent(
    name="coordinator",
    model="openai/gpt-4o",
    tools=[search],               # Own tools
    agents=[specialist],           # Sub-agents as transfer targets
    instructions="Search first, then transfer to specialist if needed.",
)
```

**Conductor mapping:** DoWhile loop (for tools) + SwitchTask (for transfers after loop).

### Hierarchical (Nested Teams)

Agents can be nested to any depth. A team lead delegates to specialists, who can themselves be teams:

```python
backend = Agent(name="backend", model="openai/gpt-4o",
                instructions="You are a backend developer.")
frontend = Agent(name="frontend", model="openai/gpt-4o",
                 instructions="You are a frontend developer.")

engineering = Agent(
    name="engineering",
    model="openai/gpt-4o",
    instructions="Route to backend or frontend.",
    agents=[backend, frontend],
    strategy="handoff",
)

marketing = Agent(...)

ceo = Agent(
    name="ceo",
    model="openai/gpt-4o",
    instructions="Route to engineering or marketing.",
    agents=[engineering, marketing],
    strategy="handoff",
)
```

**Conductor mapping:** Nested `InlineSubWorkflowTask` calls — each level compiles to its own sub-workflow.

---

## Google ADK Compatibility

The SDK includes a compatibility layer for [Google ADK](https://github.com/google/adk-python) (`google.adk.agents`). Code written for Google ADK runs on Conductor with durable execution, distributed tool scaling, and visual workflow debugging.

### Supported ADK classes

| ADK Class | Conductor Mapping |
|-----------|------------------|
| `Agent` | Single agent workflow (LLM + tool loop) |
| `SequentialAgent` | Sequential sub-workflow pipeline |
| `ParallelAgent` | FORK_JOIN with concurrent sub-workflows |
| `LoopAgent` | DO_WHILE loop over sub-agents |
| `AgentTool` | SUB_WORKFLOW invoked as a tool (⏳ needs server deploy) |

### Supported ADK features

| Feature | Status |
|---------|--------|
| `sub_agents` (handoff) | ✅ Supported |
| `instruction` / `global_instruction` | ✅ Supported |
| `output_schema` (Pydantic) | ✅ Supported |
| `output_key` | ✅ Supported |
| `generate_content_config` (temperature, max_output_tokens) | ✅ Supported |
| `FunctionTool` (Python functions) | ✅ Supported |
| `AgentTool` (agent-as-tool) | ⏳ Server code ready, needs deploy |
| `before_model_callback` / `after_model_callback` | ⏳ Server code ready, needs deploy |
| `disallow_transfer_to_parent` / `disallow_transfer_to_peers` | ⏳ Server code ready, needs deploy |
| `BuiltInPlanner` | ⏳ Server code ready, needs deploy |

See [examples/adk/](examples/adk/) for 28 working examples and [ADK_SAMPLES_STATUS.md](examples/adk/ADK_SAMPLES_STATUS.md) for full coverage tracking against Google's 45 ADK samples.

---

## Architecture

### The Agent Loop

When `run(agent, "message")` is called, the SDK compiles the Agent into this Conductor workflow:

```
START
  │
  ▼
[Init State] ── Set messages = [{role: "user", content: input}]
  │
  ▼
[Input Guardrails] ── Validate user input
  │
  ▼
┌──▶ [LLM_CHAT_COMPLETE] ── messages + tool schemas → LLM
│      │
│      ▼
│    [Output Guardrails] ── Validate LLM response
│      │
│      ▼
│    [SWITCH on response type]
│      │
│      ├── tool_call ──▶ [WAIT if approval_required]
│      │                    │
│      │                 [Execute Tool] ── Conductor schedules worker task
│      │                    │
│      │                 [Update Messages] ── Append tool result
│      │                    └──▶ (loop back)
│      │
│      ├── handoff ───▶ [SUB_WORKFLOW] ── Run sub-agent's workflow
│      │                    │
│      │                 [Update Messages] ── Append result
│      │                    └──▶ (loop back)
│      │
│      └── final_answer ──▶ (exit loop)
│
└───────────────────────────────────────────────────────┘
  │
  ▼
[Output Formatting] ── Parse structured output if output_type set
  │
  ▼
END
```

### Conductor Mapping

| SDK Concept | Conductor Primitive |
|---|---|
| `Agent` | `ConductorWorkflow` |
| `@tool` (Python function) | Task definition + `@worker_task` |
| `http_tool` | `HttpTask` (system task) |
| `mcp_tool` | `ListMcpTools` + `CallMcpTool` |
| Agent loop | `DoWhileTask` |
| LLM call | `LlmChatComplete` (system task) |
| Tool dispatch | `SwitchTask` / `DynamicTask` |
| Handoff | `InlineSubWorkflowTask` |
| Sequential | Chain of `SubWorkflowTask` |
| Parallel | `ForkTask` + `JoinTask` |
| Router | `DoWhileTask` + `SwitchTask` |
| Human approval | `WaitTask` |
| Conversation state | `workflow.variables` |
| Guardrail (custom function) | Worker task (before/after LLM) |
| Guardrail (`RegexGuardrail`) | `InlineTask` (server-side JS) |
| Guardrail (external) | `SimpleTask` (remote worker) |
| Structured output | `LlmChatComplete(output_schema=...)` |
| Session | `correlation_id` on workflow |

### Server-First Tool Execution

```
@tool decorator           Conductor Server            Worker Process
================          ================            ==============

@tool
def get_weather(...)  ──▶  Task definition
                           registered

Agent runs, LLM        ──▶  LLM_CHAT_COMPLETE
calls get_weather            returns tool_call

                           Conductor schedules
                           task in queue  ──────────▶  Worker polls,
                                                       executes get_weather()

                           Result stored    ◀──────────  Returns result
                           in workflow

                           Next LLM call
                           with tool result
```

Steps 2, 3, 5, 6 happen server-side. Only step 4 (actual tool execution) requires a running worker process.

---

## Configuration

The SDK reads configuration from environment variables:

| Variable | Description | Default |
|---|---|---|
| `AGENTSPAN_SERVER_URL` | Agentspan server API URL | `http://localhost:8080/api` |
| `AGENTSPAN_AUTH_KEY` | Auth key (Orkes Cloud) | None |
| `AGENTSPAN_AUTH_SECRET` | Auth secret (Orkes Cloud) | None |
| `AGENTSPAN_AGENT_TIMEOUT` | Default workflow timeout (seconds) | 300 |
| `AGENTSPAN_LLM_RETRY_COUNT` | LLM task retry count | 3 |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | Worker poll interval (ms) | 100 |
| `AGENTSPAN_WORKER_THREADS` | Worker threads per tool | 1 |

### Programmatic Configuration

```python
from agentspan.agents.runtime import AgentConfig, AgentRuntime

config = AgentConfig(
    server_url="http://localhost:8080/api",
    default_timeout_seconds=600,
    worker_thread_count=5,
)

runtime = AgentRuntime(config=config)
result = runtime.run(agent, "Hello")
```

---

## Testing & Validation

All changes must be validated before merging.

### Unit Tests

```bash
python3 -m pytest tests/unit/ -v
```

All unit tests must pass.

### Example Validation

All runnable examples must execute successfully against a live Conductor server (`http://localhost:8080/api`, no auth).

**Autonomous examples** (run directly):

| Example | Description |
|---------|-------------|
| `01_basic_agent.py` | Simple agent, no tools |
| `02a_simple_tools.py` | Native function calling with tools |
| `02b_multi_step_tools.py` | Multi-step tool usage |
| `03_structured_output.py` | Pydantic output types |
| `05_handoffs.py` | Multi-agent handoff strategy |
| `06_sequential_pipeline.py` | Sequential agent pipeline |
| `07_parallel_agents.py` | Parallel agent execution |
| `08_router_agent.py` | Router-based agent selection |
| `10_guardrails.py` | Input/output guardrails |
| `11_streaming.py` | Event streaming |
| `12_long_running.py` | Async/long-running agents |
| `13_hierarchical_agents.py` | Nested multi-agent teams |
| `14_existing_workers.py` | Using existing Conductor workers |
| `15_agent_discussion.py` | Round-robin agent debate |
| `16_random_strategy.py` | Random agent selection |
| `17_swarm_orchestration.py` | Swarm with handoff conditions |
| `19_composable_termination.py` | Composable termination conditions |
| `20_constrained_transitions.py` | Restricted agent transitions |
| `21_regex_guardrails.py` | RegexGuardrail (block/allow patterns) |
| `22_llm_guardrails.py` | LLMGuardrail (AI judge) |
| `23_token_tracking.py` | Token usage tracking |
| `24_code_execution.py` | Code execution sandboxes |
| `25_semantic_memory.py` | Semantic memory with retrieval |
| `28_gpt_assistant_agent.py` | OpenAI Assistants API wrapper |
| `29_agent_introductions.py` | Agent introductions |
| `30_multimodal_agent.py` | Image/video analysis |
| `31_tool_guardrails.py` | Pre-execution tool input validation |
| `33_single_turn_tool.py` | Single-turn tool calling |
| `33_external_workers.py` | External worker references |
| `34_prompt_templates.py` | Server-side prompt templates |
| `35_standalone_guardrails.py` | Guardrails as plain callables |
| `36_simple_agent_guardrails.py` | Guardrails on tool-less agents |
| `37_fix_guardrail.py` | Auto-correct with on_fail="fix" |
| `38_tech_trends.py` | Multi-agent pipeline with live HTTP tools |

**Compile-only examples** (require human interaction or external services):

| Example | Reason |
|---------|--------|
| `02_tools.py` | Requires human approval interaction |
| `04_http_and_mcp_tools.py` | Requires external HTTP/MCP servers |
| `04_mcp_weather.py` | Requires MCP server |
| `09_human_in_the_loop.py` | Requires human interaction |
| `09b_hitl_with_feedback.py` | Requires human interaction |
| `09c_hitl_streaming.py` | Requires human interaction |
| `18_manual_selection.py` | Requires human interaction |
| `26_opentelemetry_tracing.py` | Requires OTel collector |
| `27_user_proxy_agent.py` | Requires human interaction |
| `32_human_guardrail.py` | Requires human review |

### Run All Autonomous Examples

```bash
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
for ex in 01_basic_agent 02a_simple_tools 02b_multi_step_tools 03_structured_output \
          05_handoffs 06_sequential_pipeline 07_parallel_agents 08_router_agent \
          10_guardrails 11_streaming 12_long_running 13_hierarchical_agents 14_existing_workers \
          15_agent_discussion 16_random_strategy 17_swarm_orchestration \
          19_composable_termination 20_constrained_transitions \
          21_regex_guardrails 22_llm_guardrails 23_token_tracking \
          24_code_execution 25_semantic_memory 28_gpt_assistant_agent \
          29_agent_introductions 30_multimodal_agent 31_tool_guardrails \
          33_single_turn_tool 33_external_workers 34_prompt_templates \
          35_standalone_guardrails 36_simple_agent_guardrails 37_fix_guardrail \
          38_tech_trends; do
    echo "=== Running $ex ==="
    timeout 120 python3 examples/${ex}.py
done
```

### Troubleshooting

**SSL Certificate Errors on macOS**

Examples that make outbound HTTPS calls (e.g., `38_tech_trends.py`) may fail with:
```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

This happens because macOS Python framework installs do not link to system certificates by default. Fix:
```bash
# Replace 3.12 with your Python version
/Applications/Python\ 3.12/Install\ Certificates.command
```

This creates a symlink from OpenSSL's cert directory to certifi's CA bundle. Only needs to be run once per Python installation.

**PEP 563 (`from __future__ import annotations`)**

Tool functions defined in modules that use `from __future__ import annotations` are fully supported. The SDK resolves string annotations to real types via `typing.get_type_hints()` in `make_tool_worker()` at registration time.

### E2E / Integration Tests

End-to-end streaming tests validate the complete SSE event stream for all agent categories against a live Conductor server.

**Prerequisites:**
- Running Conductor server with streaming support
- `export AGENTSPAN_SERVER_URL=http://localhost:8080/api`
- LLM provider configured (OpenAI by default)
- Optionally: `export AGENT_LLM_MODEL=openai/gpt-4o-mini` (default)

**Running:**

| Command | What it runs |
|---|---|
| `python3 -m pytest tests/integration/ -m integration -v` | All integration tests |
| `python3 -m pytest tests/integration/test_e2e_streaming.py -v` | E2E streaming only |
| `python3 -m pytest tests/integration/test_e2e_streaming.py::TestHITLStreaming -v` | HITL tests only |
| `python3 -m pytest tests/ -m "not integration"` | Unit tests only (no server) |

**Test categories:**

| Category | Test Class | Validates |
|---|---|---|
| Simple agents | `TestSimpleAgentStreaming` | thinking → done |
| Tool agents | `TestToolAgentStreaming` | tool_call → tool_result cycle |
| HITL | `TestHITLStreaming` | Programmatic approve/reject/feedback |
| Handoff | `TestHandoffStreaming` | Sub-agent delegation |
| Sequential | `TestSequentialStreaming` | Pipeline (>> operator) |
| Parallel | `TestParallelStreaming` | Fan-out / fan-in |
| Router | `TestRouterStreaming` | LLM-based routing |
| Guardrails | `TestGuardrailStreaming` | guardrail_pass/fail, retry, raise |
| Manual HITL | `TestManualSelectionStreaming` | Human selects agent per turn |
| Stream API | `TestAgentStreamAPI` | AgentStream object behavior |

**How HITL tests work:** Instead of `input()` prompts, tests call `result.approve()`,
`result.reject(reason)`, or `result.respond(dict)` programmatically. The test collects
events until `WAITING`, performs the action, then continues collecting until terminal.

---

## Package Structure

```
src/agentspan/agents/
├── __init__.py                 # Public API exports
├── agent.py                    # Agent class
├── tool.py                     # @tool, ToolDef, ToolContext, http_tool, mcp_tool
├── run.py                      # run, start, stream, run_async (singleton runtime)
├── result.py                   # AgentResult, AgentHandle, AgentEvent, EventType
├── guardrail.py                # Guardrail, RegexGuardrail, LLMGuardrail, GuardrailResult
├── memory.py                   # ConversationMemory
├── runtime/
│   ├── runtime.py              # AgentRuntime (compile + execute + stream)
│   ├── tool_registry.py        # Tool/worker registration and dispatch
│   ├── _dispatch.py            # Universal dispatch worker (fuzzy parsing, circuit breaker)
│   └── mcp_discovery.py        # MCP server tool discovery
└── _internal/
    ├── model_parser.py         # Parse "provider/model" strings
    └── schema_utils.py         # JSON Schema generation from type hints

# Google ADK compatibility layer (google.adk.agents namespace)
google/adk/agents/                      # Drop-in ADK compatibility

```
