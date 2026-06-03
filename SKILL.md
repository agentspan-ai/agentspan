# Agentspan — Build Durable AI Agents

Agentspan is a distributed, durable runtime for AI agents. Agents survive crashes, scale across machines, and pause for human approval. Use Python SDK.

## Two Use Cases

**Developer building agents:** Define → deploy → serve → trigger by name. Long-lived, versioned, monitored.

**Autonomous agent building ephemeral agents:** Define → `rt.run(agent, prompt)` → get result → move on. No deploy. No serve. One call.

## Quickstart (Ephemeral — for autonomous agents)

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="helper", model="openai/gpt-4o", instructions="You are a helpful assistant.")

with AgentRuntime() as rt:
    result = rt.run(agent, "What is quantum computing?")
    print(result.output["result"])   # String output
    # Or: result.print_result()      # Pretty-printed
```

`rt.run()` handles deploy + workers + execution internally. The agent is ephemeral — created for this task, discarded after.

## Production Pattern (for developers)

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="helper", model="openai/gpt-4o", instructions="...")

if __name__ == "__main__":
    with AgentRuntime() as rt:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy my_module
        rt.deploy(agent)   # Push definition to server (idempotent)
        rt.serve(agent)    # Start workers, poll for tasks (blocks forever)
```

Trigger from outside: `agentspan run helper "What is quantum computing?"`

## Configuration

```python
# Default: reads AGENTSPAN_SERVER_URL from environment
rt = AgentRuntime()

# Explicit:
from agentspan.agents import AgentConfig
config = AgentConfig(server_url="http://localhost:6767/api", api_key="...")
rt = AgentRuntime(config=config)
```

Environment variables: `AGENTSPAN_SERVER_URL`, `AGENTSPAN_AUTH_KEY`, `AGENTSPAN_AUTH_SECRET`

## Agent

```python
Agent(
    name="my_agent",                    # Required. Unique. Alphanumeric + underscore/hyphen.
    model="openai/gpt-4o",             # "provider/model" format
    instructions="You are a ...",       # System prompt (str, callable, or PromptTemplate)
    tools=[my_tool],                    # List of @tool functions
    max_turns=25,                       # Max LLM iterations
    timeout_seconds=0,                  # 0 = no timeout
    max_tokens=None,                    # Max output tokens per LLM call
    temperature=None,                   # LLM temperature
    output_type=MyPydanticModel,        # Structured output (Pydantic model)
    planner=False,                      # Enable planning-first behavior
    thinking_budget_tokens=None,        # Extended reasoning token budget
    credentials=["API_KEY"],            # Credentials resolved from server
    metadata={"team": "backend"},       # Custom metadata
)
```

Model formats: `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4-6"`, `"google_gemini/gemini-2.5-flash"`, `"claude-code/opus"`

### @agent Decorator

```python
from agentspan.agents import agent

@agent(model="openai/gpt-4o", tools=[search])
def researcher():
    """You are a research assistant. Find and summarize information."""

# Use like: rt.run(researcher, "Find info about quantum computing")
```

The docstring becomes the instructions.

## AgentResult

```python
result = rt.run(agent, "prompt")

result.output            # Dict: {"result": "..."} or agent-specific shape
result.output["result"]  # The text output (string)
result.status            # "COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"
result.execution_id      # Execution ID
result.error             # Error message if failed, else None
result.token_usage       # {"input_tokens": N, "output_tokens": N, ...}
result.finish_reason     # "stop", "length", "error", "cancelled", "timeout", "guardrail"
result.is_success        # True if COMPLETED
result.is_failed         # True if FAILED/TERMINATED
result.sub_results       # List of sub-agent results (multi-agent)
result.print_result()    # Pretty-print the output
```

## Error Handling

```python
result = rt.run(agent, "prompt")

if result.is_success:
    print(result.output["result"])
elif result.is_failed:
    print(f"Failed: {result.error}")
    print(f"Status: {result.status}")   # FAILED, TERMINATED, TIMED_OUT
    print(f"Reason: {result.finish_reason}")
```

For autonomous agents building ephemeral agents — always check `result.is_success` before using `result.output`.

## Tools

```python
from agentspan.agents import tool

@tool
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

@tool(approval_required=True, credentials=["API_KEY"])
def delete_file(path: str) -> str:
    """Delete a file. Requires human approval."""
    os.remove(path)
    return f"Deleted {path}"
```

Tool functions must have type hints and a docstring. The schema is generated automatically.

### ToolContext (dependency injection + shared state)

```python
from agentspan.agents import tool, ToolContext

@tool
def lookup(query: str, context: ToolContext) -> str:
    """Search with context."""
    wf_id = context.execution_id
    session = context.session_id
    state = context.state          # Mutable dict shared across tool calls
    deps = context.dependencies    # From Agent(dependencies={...})
    return f"Found in execution {wf_id}"
```

`context.state` is per-execution scratch shared across all tool calls in that run — useful for accumulating items, caching API responses, or coordinating between tool invocations without round-tripping through the LLM:

```python
@tool
def add_item(item: str, context: ToolContext) -> dict:
    """Append to a shared list."""
    items = context.state.setdefault("cart", [])
    items.append(item)
    return {"added": item, "total": len(items)}

@tool
def get_cart(context: ToolContext) -> list:
    """Read the shared list."""
    return context.state.get("cart", [])
```

### Server-side tools (no local worker needed)

```python
from agentspan.agents import http_tool, mcp_tool, api_tool

weather = http_tool(
    name="get_weather",
    description="Get weather for a city",
    url="https://api.weather.com/v1/current?city=${city}",
    credentials=["WEATHER_API_KEY"],
)

github = mcp_tool(
    server_url="https://mcp.github.com",
    tool_names=["create_issue", "list_repos"],
    credentials=["GITHUB_TOKEN"],
)

stripe = api_tool(
    url="https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
    tool_names=["CreatePaymentIntent", "ListCustomers"],
    credentials=["STRIPE_SECRET_KEY"],
)
```

## Multi-Agent

All multi-agent compositions use one `Agent(...)` as the *parent* with `agents=[...]` sub-agents and a `strategy=` controlling how they're orchestrated. Parents can themselves be sub-agents of bigger parents — strategies nest freely.

### Strategy Enum

```python
from agentspan.agents import Strategy

Strategy.SEQUENTIAL    # Run in order; output of one feeds the next
Strategy.PARALLEL      # Run concurrently; results aggregated
Strategy.ROUTER        # Router agent picks ONE sub-agent to handle the input
Strategy.HANDOFF       # Parent LLM picks next sub-agent each turn (default)
Strategy.SWARM         # Peer-to-peer; sub-agents hand off via text mentions
Strategy.ROUND_ROBIN   # Cycle through sub-agents in fixed order each turn
Strategy.RANDOM        # Random sub-agent each turn (brainstorming/diversity)
Strategy.MANUAL        # Human picks who responds next (pauses each turn)
Strategy.PLAN_EXECUTE  # Planner emits JSON DAG; executor runs deterministically
```

Pass `strategy="parallel"` (string) or `strategy=Strategy.PARALLEL` — both work.

### Sequential Pipeline (>>)

```python
researcher = Agent(name="researcher", model="openai/gpt-4o", instructions="Research the topic.")
writer = Agent(name="writer", model="openai/gpt-4o", instructions="Write a summary.")

pipeline = researcher >> writer
```

### Parallel

```python
Agent(
    name="analysis",
    model="openai/gpt-4o",
    agents=[pros_agent, cons_agent],
    strategy="parallel",
)
```

### Router

```python
router_agent = Agent(name="router", model="openai/gpt-4o", instructions="Route to the right specialist.")

Agent(
    name="team",
    model="openai/gpt-4o",
    agents=[billing, technical],
    strategy="router",
    router=router_agent,
)
```

### SWARM (peer-to-peer handoff)

```python
from agentspan.agents.handoff import OnTextMention

coder = Agent(name="coder", model="openai/gpt-4o", instructions="Code. Say HANDOFF_TO_QA when done.")
qa = Agent(name="qa", model="openai/gpt-4o", instructions="Test. Say HANDOFF_TO_CODER if bugs found.")

Agent(
    name="dev_team",
    model="openai/gpt-4o",
    agents=[coder, qa],
    strategy="swarm",
    handoffs=[
        OnTextMention(text="HANDOFF_TO_QA", target="qa"),
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
    ],
)
```

### Scatter-Gather (fan-out/fan-in)

```python
from agentspan.agents import scatter_gather

coordinator = scatter_gather(
    name="multi_search",
    worker=Agent(name="searcher", model="openai/gpt-4o-mini", instructions="Search and summarize."),
    timeout_seconds=300,
)
# Spawns multiple copies of worker agent in parallel, aggregates results
```

### Round-Robin / Random / Manual

```python
Agent(agents=[a, b, c], strategy=Strategy.ROUND_ROBIN, max_turns=6)   # a→b→c→a→b→c
Agent(agents=[a, b, c], strategy=Strategy.RANDOM, max_turns=6)        # random each turn
Agent(agents=[a, b, c], strategy=Strategy.MANUAL, max_turns=6)        # human picks via handle.respond({"selected": "b"})
```

### Handoff (LLM-driven dispatch)

```python
# Default strategy: the parent LLM uses its instructions to pick which sub-agent runs next.
ceo = Agent(
    name="ceo",
    model="openai/gpt-4o",
    instructions="Delegate eng tasks to engineering_lead, marketing tasks to marketing_lead.",
    agents=[engineering_lead, marketing_lead],
    strategy=Strategy.HANDOFF,
)
```

### Hierarchical Teams (nested strategies)

Sub-agents can themselves be multi-agent. Compose freely:

```python
# Leaves
backend_dev = Agent(name="backend", model=MODEL, instructions="Backend specialist.")
frontend_dev = Agent(name="frontend", model=MODEL, instructions="Frontend specialist.")
writer = Agent(name="writer", model=MODEL, instructions="Write copy.")
seo = Agent(name="seo", model=MODEL, instructions="SEO expert.")

# Mid-level leads (each is a small team)
eng_lead = Agent(name="eng_lead", model=MODEL, agents=[backend_dev, frontend_dev], strategy=Strategy.HANDOFF)
mkt_lead = Agent(name="mkt_lead", model=MODEL, agents=[writer, seo], strategy=Strategy.PARALLEL)

# Top-level orchestrator
ceo = Agent(name="ceo", model=MODEL, agents=[eng_lead, mkt_lead], strategy=Strategy.HANDOFF,
            instructions="Route eng work to eng_lead, marketing to mkt_lead.")
```

Mix and match — `parallel >> sequential`, `router → swarm`, etc. The `>>` operator works on any agent (single or composite).

### Agent as Tool

```python
from agentspan.agents import agent_tool

specialist = Agent(name="math_expert", model="openai/gpt-4o", instructions="Solve math problems.")

orchestrator = Agent(
    name="orchestrator",
    model="openai/gpt-4o",
    instructions="Delegate math to the specialist.",
    tools=[agent_tool(specialist, description="Call the math expert")],
)
```

## Guardrails

```python
from agentspan.agents import RegexGuardrail, LLMGuardrail, Guardrail, GuardrailResult

# Regex: block emails in output
RegexGuardrail(
    name="no_emails",
    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
    message="Remove email addresses.",
    on_fail="retry",    # retry | raise | fix | human
    max_retries=3,
)

# LLM: policy-based check
LLMGuardrail(
    name="safety",
    model="openai/gpt-4o-mini",
    policy="Reject responses with medical advice.",
    on_fail="raise",
)

# Custom function
def no_ssn(content: str) -> GuardrailResult:
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", content):
        return GuardrailResult(passed=False, message="Redact SSNs.")
    return GuardrailResult(passed=True)

Guardrail(no_ssn, position="output", on_fail="retry", max_retries=3)
```

## Termination Conditions

```python
from agentspan.agents import TextMentionTermination, MaxMessageTermination

Agent(
    name="worker",
    model="openai/gpt-4o",
    instructions="Say DONE when finished.",
    termination=TextMentionTermination("DONE"),
    # OR: termination=MaxMessageTermination(10),
    # Composable: termination=TextMentionTermination("DONE") | MaxMessageTermination(10),
)
```

## Gates (Conditional Pipelines)

```python
from agentspan.agents.gate import TextGate

checker = Agent(name="checker", model="openai/gpt-4o",
    instructions="Output NO_ISSUES if everything is fine.",
    gate=TextGate("NO_ISSUES"),  # Stops pipeline if text present
)
fixer = Agent(name="fixer", model="openai/gpt-4o", instructions="Fix the issue.")

pipeline = checker >> fixer  # fixer only runs if checker finds issues
```

## Memory

```python
from agentspan.agents import ConversationMemory, SemanticMemory

# Conversation memory (chat history with windowing)
agent = Agent(
    name="chatbot",
    model="openai/gpt-4o",
    memory=ConversationMemory(max_messages=50),
)

# Semantic memory (long-term, searchable)
memory = SemanticMemory()
memory.add("User prefers Python over JavaScript")
memory.add("User works at Acme Corp")
results = memory.search("What language does the user prefer?")
```

## Claude Code Agents

```python
from agentspan.agents import Agent, ClaudeCode

# Simple: slash syntax
reviewer = Agent(
    name="reviewer",
    model="claude-code/sonnet",
    instructions="Review code for quality.",
    tools=["Read", "Glob", "Grep"],     # Built-in Claude tools (strings only)
    max_turns=10,
)

# With config
reviewer = Agent(
    name="reviewer",
    model=ClaudeCode("opus", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
    instructions="Review code.",
    tools=["Read", "Edit", "Bash"],
)
```

Available tools: `Read`, `Edit`, `Write`, `Bash`, `Glob`, `Grep`, `WebSearch`, `WebFetch`

## CLI Execution

```python
Agent(
    name="deployer",
    model="openai/gpt-4o",
    instructions="Use git and gh to manage repos.",
    cli_commands=True,
    cli_allowed_commands=["git", "gh", "curl"],
    credentials=["GITHUB_TOKEN"],
)
```

## Schedules (Cron Triggers)

Attach one or more cron triggers to an agent at deploy time. The scheduler fires the agent on its cadence with the supplied input.

```python
from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.schedule import Schedule

agent = Agent(name="hello", model="openai/gpt-4o-mini", instructions="Say hi.")

with AgentRuntime() as rt:
    rt.deploy(
        agent,
        schedules=[
            Schedule(
                name="every-5s",                 # short id, unique per agent
                cron="0/5 * * * * ?",            # 6-field Quartz cron (sec min hr dom mon dow)
                input={"prompt": "Say hi."},     # input on each fire
                timezone="UTC",                  # IANA tz (optional)
                description="demo cadence",
                paused=False,                    # start active
                catchup=False,                   # don't replay missed fires
            ),
        ],
    )
    rt.serve(agent, blocking=False)   # workers must be up for LLM tasks to run
```

Wire name on the server is `{agent.name}-{schedule.name}`. List, pause/resume, or remove schedules via `rt.schedules_client().reconcile(agent.name, [...])` — pass `[]` to delete all. Cron is 6-field Quartz (seconds field required).

## Code Execution

```python
Agent(
    name="data_scientist",
    model="openai/gpt-4o",
    instructions="Write and run Python code to analyze data.",
    local_code_execution=True,
    allowed_languages=["python"],
)
```

## Credentials

Credentials are always resolved from the server. No env var fallback. Missing credentials cause `FAILED_WITH_TERMINAL_ERROR` (non-retryable).

```bash
# Store credentials on server
agentspan credentials set --name GITHUB_TOKEN
agentspan credentials set --name OPENAI_API_KEY
```

```python
Agent(
    name="github_agent",
    model="openai/gpt-4o",
    credentials=["GITHUB_TOKEN"],  # Resolved at tool execution time
    tools=[my_github_tool],
)
```

## Callbacks

```python
from agentspan.agents import CallbackHandler

class MyCallbacks(CallbackHandler):
    def on_agent_start(self, **kwargs): pass
    def on_agent_end(self, **kwargs): pass
    def on_model_start(self, **kwargs): pass
    def on_model_end(self, **kwargs): pass

Agent(name="agent", model="openai/gpt-4o", callbacks=[MyCallbacks()])
```

## Streaming & Human-in-the-Loop

Use `rt.start()` + `handle.stream()` to react to events as they fire — required for interactive HITL (approval tools).

```python
from agentspan.agents import EventType

with AgentRuntime() as rt:
    handle = rt.start(agent, "Transfer $500 from A to B")
    for event in handle.stream():
        if event.type == EventType.THINKING:
            print("thinking:", event.content)
        elif event.type == EventType.TOOL_CALL:
            print("tool_call:", event.tool_name, event.args)
        elif event.type == EventType.TOOL_RESULT:
            print("tool_result:", event.tool_name, event.result)
        elif event.type == EventType.WAITING:
            # Approval-required tool is paused — inspect schema and respond
            status = handle.get_status()
            schema = (status.pending_tool or {}).get("response_schema", {})
            handle.respond({"approved": True})       # shape matches schema
        elif event.type == EventType.DONE:
            print("done:", event.output)
```

`handle` also supports `.pause()`, `.resume()`, `.cancel(reason)`, `.get_status()`.

## Plan-Execute Strategy

For LLM-generated plans that should run deterministically (DAG compiled into a Conductor workflow):

```python
from agentspan.agents import plan_execute, Agent, tool

planner = Agent(name="planner", model="openai/gpt-4o", instructions="Produce a JSON plan...")
fallback = Agent(name="fixer", model="openai/gpt-4o", instructions="Repair failed plan.")

orchestrator = plan_execute(
    name="report_builder",
    planner=planner,
    tools=[write_file, read_file],   # tools usable by plan ops
    fallback=fallback,                # optional: runs if validation fails
)
rt.run(orchestrator, "Write a report on AI agents")
```

The planner emits a JSON fence describing a DAG; the executor compiles it and runs each op (static tool call or scoped LLM call) deterministically.

## CLI Deploy

Recommended for CI/CD — no Python imports needed at deploy time:

```bash
agentspan deploy --package my_package.my_module     # registers all Agent objects in module
agentspan run agent_name "prompt text"              # trigger a deployed agent
agentspan credentials set --name OPENAI_API_KEY     # store a credential on the server
```

## Structured Output

```python
from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    summary: str

Agent(name="analyzer", model="openai/gpt-4o", output_type=Analysis)
```

## Framework Integration

### LangGraph

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o")
graph = create_react_agent(llm, tools=[my_tool])

with AgentRuntime() as rt:
    result = rt.run(graph, "What is 15 * 7?")  # Ephemeral
    # Or production: rt.deploy(graph); rt.serve(graph)
```

### OpenAI Agents SDK

```python
from agents import Agent as OpenAIAgent
from agentspan.agents import AgentRuntime

agent = OpenAIAgent(name="helper", instructions="...", model="gpt-4o")

with AgentRuntime() as rt:
    result = rt.run(agent, "Hello")  # Ephemeral
```

## Execution API

```python
with AgentRuntime() as rt:
    # ── Ephemeral (autonomous agents) ──────────────────────
    result = rt.run(agent, "prompt")                    # Sync: deploy + run + cleanup
    result = await rt.run_async(agent, "prompt")        # Async variant

    # ── With options ───────────────────────────────────────
    result = rt.run(agent, "prompt",
        session_id="conv-123",                          # Multi-turn conversation
        media=["https://example.com/image.png"],        # Multimodal input
        timeout=60000,                                  # Timeout in ms
        credentials=["MY_API_KEY"],                     # Runtime credentials
    )

    # ── Streaming ──────────────────────────────────────────
    stream = rt.stream(agent, "prompt")                 # Sync stream
    for event in stream:
        print(event.type, event.content)
    result = stream.get_result()

    stream = await rt.stream_async(agent, "prompt")     # Async stream

    # ── Non-blocking ───────────────────────────────────────
    handle = rt.start(agent, "prompt")                  # Returns immediately
    status = rt.get_status(handle.execution_id)           # Poll status
    handle.pause()                                       # Pause execution
    handle.resume()                                      # Resume
    handle.cancel("no longer needed")                    # Cancel

    # ── By name (trigger deployed agent) ───────────────────
    result = rt.run("agent_name", "prompt")

    # ── Production ─────────────────────────────────────────
    rt.deploy(agent)                                     # Push definition
    rt.serve(agent)                                      # Start workers (blocks)
```

## Key Rules

1. **Agent names must be unique** — alphanumeric, underscore, hyphen. Start with letter or underscore.
2. **Tools need type hints + docstring** — schema is auto-generated
3. **`result.output` is a dict** — use `result.output["result"]` for the text, or `result.print_result()`
4. **Always check `result.is_success`** — especially in autonomous agent flows
5. **Credentials come from server** — no env var fallback, `FAILED_WITH_TERMINAL_ERROR` if missing
6. **Deploy is idempotent** — safe to call on every startup
7. **Serve blocks forever** — run triggering comes from outside (CLI, API, another process)
8. **`rt.run()` is self-contained** — handles deploy + workers + execution. Use for ephemeral agents.
9. **Claude Code tools are strings** — `["Read", "Edit", "Bash"]`, not @tool functions
10. **Schedules attach at deploy time** — `rt.deploy(agent, schedules=[Schedule(...)])`; wire name is `{agent}-{schedule.name}`; cron is 6-field Quartz (seconds field required)
11. **HITL requires streaming** — use `rt.start()` + `handle.stream()` to handle `EventType.WAITING` for approval tools; `rt.run()` will block indefinitely on a pending human task
12. **Workers must be running for LLM tasks** — even scheduled agents need `rt.serve(agent, blocking=False)` (or a separate serve process) so the agent loop can execute

## Complete Worked Example (all features combined)

A research-and-publish pipeline showing tools, server-side tools, shared state, parallel sub-agents, a gate, guardrails, HITL approval, structured output, and a cron schedule.

```python
from pydantic import BaseModel
from agentspan.agents import (
    Agent, AgentRuntime, Strategy, tool, http_tool, agent_tool,
    RegexGuardrail, LLMGuardrail, EventType, ToolContext,
)
from agentspan.agents.gate import TextGate
from agentspan.agents.schedule import Schedule


# 1. Tools — local Python + server-side HTTP
@tool
def remember(fact: str, context: ToolContext) -> str:
    """Stash a fact in shared per-execution state."""
    context.state.setdefault("facts", []).append(fact)
    return f"saved ({len(context.state['facts'])} total)"

@tool(approval_required=True)
def publish(title: str, body: str) -> dict:
    """Publish an article. Requires human approval."""
    return {"status": "published", "title": title}

fetch_news = http_tool(
    name="fetch_news",
    description="Fetch latest headlines on a topic",
    url="https://api.news.example/v1/search?q=${query}",
    credentials=["NEWS_API_KEY"],
)

# 2. Structured output for the writer
class Article(BaseModel):
    title: str
    body: str
    tags: list[str]

# 3. Parallel research phase (two specialists run concurrently)
market = Agent(name="market", model="openai/gpt-4o-mini", tools=[fetch_news, remember],
               instructions="Research market signals. Save findings with remember().")
risk = Agent(name="risk", model="openai/gpt-4o-mini", tools=[remember],
             instructions="Identify risks. Save findings with remember().")

research = Agent(name="research_phase", model="openai/gpt-4o-mini",
                 agents=[market, risk], strategy=Strategy.PARALLEL)

# 4. Quality gate — skip writing if research is empty
quality_check = Agent(
    name="quality_check", model="openai/gpt-4o-mini",
    instructions="Output NO_SIGNAL if the research lacks substance. Otherwise summarize.",
    gate=TextGate("NO_SIGNAL"),
)

# 5. Writer with structured output + guardrails
writer = Agent(
    name="writer", model="openai/gpt-4o",
    instructions="Synthesize the research into an article.",
    output_type=Article,
    tools=[publish],
    guardrails=[
        RegexGuardrail(name="no_emails", patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
                       message="Remove emails.", on_fail="retry", max_retries=2),
        LLMGuardrail(name="safety", model="openai/gpt-4o-mini",
                     policy="Reject content with PII or medical advice.", on_fail="raise"),
    ],
)

# 6. Compose: research (parallel) → quality_check (gate) → writer (publishes via HITL)
pipeline = research >> quality_check >> writer

# 7. Deploy + schedule daily; stream to handle the approval pause
if __name__ == "__main__":
    with AgentRuntime() as rt:
        rt.deploy(pipeline, schedules=[
            Schedule(name="daily-9am", cron="0 0 9 * * ?",
                     input={"prompt": "AI agents in production"}),
        ])
        rt.serve(pipeline, blocking=False)

        # Ad-hoc trigger with HITL approval handling
        handle = rt.start(pipeline, "Today's signals in AI agents")
        for event in handle.stream():
            if event.type == EventType.WAITING:
                handle.respond({"approved": True})    # auto-approve in demo
            elif event.type == EventType.DONE:
                print(event.output)                   # Article dict
                break
```

What this demonstrates:
- **Tools**: local `@tool` with shared state via `context.state`, approval-gated tool, server-side `http_tool` with credentials.
- **Multi-agent**: parallel research → sequential pipeline → handoff to writer.
- **Gate**: `quality_check` short-circuits the pipeline if research is empty.
- **Guardrails**: regex + LLM, with retry and raise behaviors.
- **Structured output**: writer returns a typed `Article`.
- **HITL**: `publish` pauses the workflow; streaming consumer responds via `handle.respond()`.
- **Schedule**: cron fires the whole pipeline daily.
- **Production wiring**: `rt.deploy(...)` registers everything, `rt.serve(..., blocking=False)` starts workers.

## Build Recipes (when to reach for what)

| Need | Construct |
|---|---|
| Single LLM call | `Agent(name, model, instructions)` + `rt.run` |
| Tool-using agent | add `tools=[@tool funcs]` |
| Server-side HTTP/MCP/OpenAPI tools (no worker) | `http_tool`, `mcp_tool`, `api_tool` |
| Multi-step pipeline | `a >> b >> c` (sequential) |
| Concurrent specialists | `Agent(agents=[...], strategy="parallel")` |
| Pick one of N specialists | `strategy="router"` + `router=Agent(...)` |
| Peer handoff via mention | `strategy="swarm"` + `handoffs=[OnTextMention(...)]` |
| Fan-out N workers | `scatter_gather(worker=Agent(...))` |
| Delegate inside an agent | `agent_tool(specialist)` in `tools=` |
| Approval gating | `@tool(approval_required=True)` + `handle.stream()` |
| Stop on condition | `termination=TextMentionTermination("DONE")` |
| Skip downstream step | `gate=TextGate("NO_ISSUES")` |
| Validate output | `RegexGuardrail` / `LLMGuardrail` / `Guardrail(fn)` |
| Persistent chat history | `memory=ConversationMemory(...)` |
| Codebase-aware agent | `model="claude-code/sonnet"` + string tools |
| Run shell | `cli_commands=True, cli_allowed_commands=[...]` |
| Run Python/bash sandboxed | `local_code_execution=True` |
| Cron trigger | `Schedule(...)` in `rt.deploy(agent, schedules=[...])` |
| LLM-planned DAG | `plan_execute(planner=..., tools=...)` |
| Structured result | `output_type=PydanticModel` |
| External framework (LangGraph/OpenAI Agents) | pass the framework's graph/agent to `rt.run` directly |
