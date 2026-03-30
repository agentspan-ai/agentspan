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

### ToolContext (dependency injection)

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
