# Writing agents

Everything is an `Agent`. A single agent wraps an LLM plus tools. An agent with
sub-agents is a multi-agent system. Compose, then run with an
[`AgentRuntime`](advanced.md).

- [Defining an agent](#defining-an-agent)
- [Instructions (static, dynamic, templated)](#instructions)
- [Tools](#tools)
- [Built-in tools](#built-in-tools)
- [Multi-agent strategies](#multi-agent-strategies)
- [Handoffs (swarm)](#handoffs-swarm)
- [Guardrails](#guardrails)
- [Termination and TextGate](#termination-and-textgate)
- [Callbacks](#callbacks)
- [Streaming and human-in-the-loop](#streaming-and-human-in-the-loop)
- [Schedules](#schedules)
- [Agents from a class (`Agent.from_instance`)](#agents-from-a-class)
- [Stateful agents](#stateful-agents)

## Defining an agent

Two equivalent ways: the `Agent` class, or the `@agent` decorator.

### The `Agent` class

```python
from conductor.ai.agents import Agent

agent = Agent(
    name="greeter",                       # required; [a-zA-Z_][a-zA-Z0-9_-]*
    model="openai/gpt-4o",                # "provider/model"
    instructions="You are a friendly assistant.",
    tools=[],                             # @tool functions or ToolDef
    max_turns=25,                         # agent-loop iteration cap
    temperature=None,
    max_tokens=None,
)
```

Common constructor arguments: `name`, `model`, `instructions`, `tools`, `agents`,
`strategy`, `guardrails`, `output_type`, `termination`, `handoffs`, `callbacks`,
`max_turns`, `max_tokens`, `temperature`, `reasoning_effort`,
`thinking_budget_tokens`, `credentials`, `stateful`, `include_contents`,
`timeout_seconds`. See the [API reference](api-reference.md#agent) for the full list.

### The `@agent` decorator

The docstring becomes the instructions. The decorated function stays callable.

```python
from conductor.ai.agents import agent, tool

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"

@agent(model="openai/gpt-4o", tools=[get_weather])
def weatherbot():
    """You are a weather assistant."""
```

A `@agent` function resolves to an `Agent` automatically when passed as a sub-agent
or to `runtime.run(...)`. When `model` is omitted it inherits the parent's model.

## Instructions

Instructions can be a string, a callable, or a server-side `PromptTemplate`.

```python
# Static string
Agent(name="a", model="openai/gpt-4o", instructions="You are concise.")

# Dynamic — a @agent function that RETURNS a string is used as instructions
@agent(model="openai/gpt-4o")
def planner():
    rules = load_rules()                 # evaluated at resolution/compile time
    return f"You are a planner. Follow these rules:\n{rules}"

# Named server-side template
from conductor.ai.agents import Agent, PromptTemplate
Agent(name="t", model="openai/gpt-4o",
      instructions=PromptTemplate(name="support_prompt",
                                  variables={"tier": "${workflow.input.user_tier}"}))
```

`PromptTemplate` references a template already stored on the server (managed via the
Conductor UI/API); the SDK does not create templates.

## Tools

Decorate a plain function with `@tool`. Type hints and the docstring generate the
tool's JSON schema. Tools run as durable Conductor worker tasks.

```python
from conductor.ai.agents import tool

@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression."""
    return {"result": eval(expression, {"__builtins__": {}}, {})}

@tool(approval_required=True, timeout_seconds=60, retry_count=2)
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email."""        # pauses for human approval before running
    return {"status": "sent", "to": to}

agent = Agent(name="assistant", model="openai/gpt-4o",
              tools=[calculate, send_email])
```

`@tool` keyword arguments: `name`, `external`, `approval_required`,
`timeout_seconds`, `guardrails`, `credentials`, `stateful`, `max_calls`,
`retry_count=2`, `retry_delay_seconds=2`, `retry_policy="linear_backoff"`.

### Tool context

A tool can receive execution context by declaring a `ToolContext` parameter; tools
without it are unchanged.

```python
from conductor.ai.agents import tool, ToolContext

@tool
def remember(note: str, context: ToolContext) -> str:
    context.state["last_note"] = note          # session_id, execution_id, state, ...
    return "noted"
```

### Inspecting tool defs — `ToolRegistry` / `get_tool_defs`

Each `@tool` function carries a resolved `ToolDef` (accessible via `get_tool_def`).
`get_tool_defs(tools)` extracts them from a mixed list. The runtime's `ToolRegistry`
registers tool functions as Conductor workers; you normally never touch it directly —
the runtime does it for you when you `run`/`serve`/`deploy`.

```python
from conductor.ai.agents.tool import get_tool_def, get_tool_defs
defs = get_tool_defs([calculate, send_email])
print(defs[0].name, defs[0].input_schema)
```

## Built-in tools

These constructors return `ToolDef`s that compile to native Conductor tasks — most
need no worker process. Add them to `tools=[...]`.

| Constructor | Purpose |
|---|---|
| `http_tool(name, description, url, method="GET", headers=None, input_schema=None, credentials=None, ...)` | Call an HTTP endpoint (HttpTask) |
| `api_tool(url, name=None, headers=None, tool_names=None, max_tools=64, credentials=None)` | Expand an OpenAPI/Swagger/Postman spec into tools |
| `mcp_tool(server_url, name=None, headers=None, tool_names=None, max_tools=64, credentials=None)` | Expose tools from an MCP server |
| `human_tool(name, description, input_schema=None)` | Pause for human input (HUMAN task) |
| `image_tool(name, description, llm_provider, model, ...)` | Generate images |
| `audio_tool(name, description, llm_provider, model, ...)` | Generate audio / TTS |
| `video_tool(name, description, llm_provider, model, ...)` | Generate video |
| `pdf_tool(name="generate_pdf", description=..., ...)` | Generate a PDF from markdown |
| `index_tool(name, description, vector_db, index, embedding_model_provider, embedding_model, ...)` | Index documents into a vector DB (RAG ingest) |
| `search_tool(name, description, vector_db, index, embedding_model_provider, embedding_model, max_results=5, ...)` | Search a vector DB (RAG query) |
| `wait_for_message_tool(name, description, batch_size=1, blocking=True)` | Dequeue from the workflow message queue |
| `agent_tool(agent, name=None, description=None, retry_count=None, retry_delay_seconds=None, optional=None)` | Call another `Agent` as a tool (sub-workflow) |

```python
from conductor.ai.agents import Agent, http_tool, mcp_tool, agent_tool

weather = http_tool(
    name="weather", description="Current weather",
    url="https://api.example.com/weather", method="GET",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
)

mcp = mcp_tool(server_url="https://mcp.example.com/sse")

sub = Agent(name="researcher", model="openai/gpt-4o", instructions="Research a topic.")
main = Agent(name="lead", model="openai/gpt-4o", tools=[weather, mcp, agent_tool(sub)])
```

### RAG (`index_tool` + `search_tool`)

`index_tool` writes embeddings into a vector DB; `search_tool` queries it. Both
compile to native Conductor LLM index/search tasks — give the agent both to build a
retrieval loop.

### OCG retrieval sub-agent

`ocg_agent(...)` builds a prebuilt retrieval `Agent` over an Open Context Graph; its
tools compile to plain HTTP tasks. `ocg_tools(...)` returns the raw `ToolDef`s if you
want to assemble your own retriever.

```python
from conductor.ai.agents import Agent, agent_tool
from conductor.ai.agents.ocg import ocg_agent

retriever = ocg_agent(model="anthropic/claude-sonnet-4-6",
                      url="https://ocg.example.com", credential="OCG_KEY")
main = Agent(name="support", model="openai/gpt-4o", tools=[agent_tool(retriever)])
```

`url` is required and binds the instance; `credential` names a server-side credential
(the secret never appears in code). Agents bound to different OCG instances must use
distinct `name`s.

## Multi-agent strategies

Pass sub-agents via `agents=[...]` and pick a `strategy`. Strategy values
(`Strategy` enum or plain strings):

| Strategy | Behavior |
|---|---|
| `HANDOFF` (default) | Parent LLM delegates to the right specialist (sub-agents appear as callable tools) |
| `SEQUENTIAL` | Run sub-agents in order, piping output forward |
| `PARALLEL` | Run sub-agents concurrently, then aggregate |
| `ROUTER` | A `router` (Agent or callable) picks one sub-agent per turn |
| `ROUND_ROBIN` | Cycle through sub-agents |
| `RANDOM` | Pick a sub-agent at random |
| `SWARM` | Sub-agents transfer control via [handoffs](#handoffs-swarm) |
| `MANUAL` | Caller selects the next agent |
| `PLAN_EXECUTE` | A planner emits a JSON plan that is executed deterministically — see [Advanced](advanced.md#plans-and-plan_execute) |

```python
from conductor.ai.agents import Agent, Strategy

billing = Agent(name="billing", model="openai/gpt-4o", instructions="Billing.")
tech    = Agent(name="technical", model="openai/gpt-4o", instructions="Tech support.")

support = Agent(
    name="support", model="openai/gpt-4o",
    instructions="Route the request to the right specialist.",
    agents=[billing, tech],
    strategy=Strategy.HANDOFF,
)
```

Sequential pipelines also have a shorthand with `>>`:

```python
pipeline = extract >> summarize >> translate     # Strategy.SEQUENTIAL
```

`scatter_gather(name, worker, ...)` builds a coordinator that fans a problem out to N
parallel copies of `worker` (via `agent_tool`) and synthesizes the results.

## Handoffs (swarm)

With `strategy="swarm"`, declare `handoffs=[...]` rules that transfer control between
agents after a tool call or after the LLM speaks.

```python
from conductor.ai.agents import Agent
from conductor.ai.agents.handoff import OnTextMention, OnToolResult, OnCondition

refund = Agent(name="refund", model="openai/gpt-4o", instructions="Process refunds.")

support = Agent(
    name="support", model="openai/gpt-4o", instructions="Help the customer.",
    agents=[refund], strategy="swarm",
    handoffs=[
        OnToolResult(tool_name="check_order", target="refund"),               # after a tool runs
        OnToolResult(tool_name="check_order", target="refund", result_contains="late"),
        OnTextMention(text="refund", target="refund"),                        # LLM output contains text (case-insensitive)
        OnCondition(condition=lambda ctx: ctx.get("iteration", 0) > 5,        # custom predicate
                    target="refund"),
    ],
)
```

`allowed_transitions={"a": ["b", "c"]}` constrains which agent may follow which.

## Guardrails

Guardrails validate input or output. They compile to worker tasks before/after the
LLM call. Decorate a `(str) -> GuardrailResult` function, or use the prebuilt
`RegexGuardrail` / `LLMGuardrail`.

```python
from conductor.ai.agents import Agent, guardrail, GuardrailResult, RegexGuardrail, LLMGuardrail, Guardrail

@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject responses containing an SSN."""
    import re
    if re.search(r"\d{3}-\d{2}-\d{4}", content):
        return GuardrailResult(passed=False, message="Remove the SSN.")
    return GuardrailResult(passed=True)

no_emails = RegexGuardrail(patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
                           name="no_emails", message="No email addresses.")

safety = LLMGuardrail(model="anthropic/claude-sonnet-4-6",
                      policy="Reject harmful or discriminatory content.")

agent = Agent(name="safe", model="openai/gpt-4o",
              guardrails=[Guardrail(no_pii, position="output", on_fail="retry"),
                          no_emails, safety])
```

`Guardrail(func, position="input"|"output", on_fail="retry"|"raise"|"fix"|"human",
name=None, max_retries=3)`. On `on_fail="retry"` the failure message is fed back to
the LLM and it tries again; `"human"` (output only) pauses for a human;
`"fix"` substitutes `GuardrailResult.fixed_output`.

## Termination and TextGate

`termination=` accepts a composable `TerminationCondition`. Combine with `&` (all)
and `|` (any).

```python
from conductor.ai.agents import (
    Agent, TextMentionTermination, MaxMessageTermination,
    TokenUsageTermination, StopMessageTermination,
)

stop = TextMentionTermination("DONE") | MaxMessageTermination(50)
stop = StopMessageTermination("TERMINATE") & TokenUsageTermination(max_total_tokens=10_000)

agent = Agent(name="loop", model="openai/gpt-4o", termination=stop)
```

- `TextMentionTermination(text, case_sensitive=False)` — substring match in output.
- `StopMessageTermination(stop_message="TERMINATE")` — exact (stripped) match.
- `MaxMessageTermination(max_messages)` — message/iteration cap.
- `TokenUsageTermination(max_total_tokens=, max_prompt_tokens=, max_completion_tokens=)`.

`TextGate` stops a `>>` pipeline early when an agent's output contains a sentinel,
compiled server-side (no worker round-trip):

```python
from conductor.ai.agents.gate import TextGate
stage = Agent(name="triage", model="openai/gpt-4o", gate=TextGate("ESCALATE"))
```

## Callbacks

Subclass `CallbackHandler` to hook the lifecycle. Each method receives keyword
arguments from the server and returns `None` to continue or a non-empty `dict` to
short-circuit (e.g. override the LLM response). Multiple handlers chain in list order.

```python
from conductor.ai.agents import Agent, CallbackHandler

class Logger(CallbackHandler):
    def on_model_start(self, **kwargs):
        print("calling LLM with", len(kwargs.get("messages", [])), "messages")
        return None                       # continue
    def on_tool_end(self, **kwargs):
        print("tool", kwargs.get("tool_name"), "done")
        return None

agent = Agent(name="watched", model="openai/gpt-4o", callbacks=[Logger()])
```

Hook points: `on_agent_start`, `on_agent_end`, `on_model_start`, `on_model_end`,
`on_tool_start`, `on_tool_end`. (The old `before_model_callback`/`after_model_callback`
constructor args are deprecated — use `callbacks=[...]`.)

## Streaming and human-in-the-loop

`runtime.start(...)` returns an [`AgentHandle`](api-reference.md#agenthandle); iterate
`handle.stream()` for [`AgentEvent`](api-reference.md#agentevent)s. When a tool needs
human approval (`@tool(approval_required=True)`) or input (`human_tool`), the stream
emits a `WAITING` event and the workflow pauses.

```python
from conductor.ai.agents import Agent, AgentRuntime, EventType, tool

@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer money; pauses for human approval first."""
    return {"status": "completed", "amount": amount}

agent = Agent(name="banker", model="openai/gpt-4o", tools=[transfer_funds])

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Transfer $500 from ACC-1 to ACC-2.")
    for event in handle.stream():
        if event.type == EventType.TOOL_CALL:
            print("tool_call", event.tool_name, event.args)
        elif event.type == EventType.WAITING:
            handle.approve()              # or handle.reject("not authorized")
        elif event.type == EventType.DONE:
            print("done:", event.output)
```

HITL methods on the handle (and on a stream):

- `approve(*, event=None)` — approve the pending tool call.
- `reject(reason="", *, event=None)` — reject it.
- `respond(output, *, event=None)` — answer a `human_tool` with arbitrary fields.
- `send(message, *, event=None)` — push a message to a waiting (multi-turn) agent.

Pass `event=<the WAITING event>` to target a specific pending pause when more than one
is in flight (event-targeted approval):

```python
for event in handle.stream():
    if event.type == EventType.WAITING:
        handle.approve(event=event)       # approve exactly this pending call
```

`runtime.run(agent, prompt, on_event=callback)` runs synchronously while streaming
events to `callback`. Async variants: `runtime.stream_async`, `await handle.approve_async(...)`,
`handle.stream_async()`.

`EventType` values: `THINKING`, `TOOL_CALL`, `TOOL_RESULT`, `HANDOFF`, `WAITING`,
`MESSAGE`, `ERROR`, `DONE`, `GUARDRAIL_PASS`, `GUARDRAIL_FAIL`.

## Schedules

Run an agent on a cron schedule. Define `Schedule`s and attach them at deploy time, or
manage them through the schedule client.

```python
from conductor.ai.agents import AgentRuntime, Schedule

nightly = Schedule(name="nightly", cron="0 0 * * *", timezone="UTC",
                   input={"prompt": "Summarize today's tickets."})

with AgentRuntime() as runtime:
    runtime.deploy(agent, schedules=[nightly])     # upsert these, prune the rest
```

`schedules=[]` purges all schedules for the agent; omitting `schedules` leaves them
untouched. The schedule lifecycle client (`runtime.schedules_client()` or
`runtime.client.schedules`) exposes `save`, `get`, `list_for_agent`, `pause`,
`resume`, `delete`, `run_now`, `preview_next`, `reconcile`. See
[Advanced](advanced.md) and the [API reference](api-reference.md#schedule).

## Agents from a class

`Agent.from_instance(obj)` turns `@agent`-decorated **methods** on an object into
agents — handy for dependency injection and grouping related agents, tools, and
guardrails on one class. `@tool` and `@guardrail` methods on the same instance are
auto-attached (bound to `self`).

```python
from conductor.ai.agents import Agent, agent, tool

class Support:
    def __init__(self, db):
        self.db = db

    @tool
    def lookup(self, order_id: str) -> dict:
        """Look up an order."""
        return self.db.get(order_id)

    @agent(model="openai/gpt-4o")
    def triage(self):
        """Triage the request and answer using the lookup tool."""

support = Support(db=my_db)

one = Agent.from_instance(support, "triage")   # a single Agent by name
allg = Agent.from_instance(support)            # list[Agent], one per @agent method
```

Sub-agents can be referenced by method name as strings in the `@agent`'s `agents=`
list; they resolve against sibling `@agent` methods (cycles raise). A method returning
a string provides dynamic instructions; returning an `Agent` makes it a factory.

## Stateful agents

Set `stateful=True` to scope the agent's (and its tools') worker tasks to a per-run
domain so state isn't shared across concurrent executions. Use it when a tool holds
per-execution state.

```python
agent = Agent(name="session_agent", model="openai/gpt-4o",
              tools=[remember], stateful=True)
```

For conversational continuity across `run` calls, pass a `session_id`:

```python
runtime.run(agent, "My name is Ada.", session_id="user-42")
runtime.run(agent, "What's my name?", session_id="user-42")
```
