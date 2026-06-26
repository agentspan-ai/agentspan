# Framework agents

Conductor Agent can run agents authored in other frameworks by bridging them onto its
durable runtime. You keep your framework's authoring API; Conductor Agent handles
durability, retries, streaming, and observability.

Supported bridges: **OpenAI Agents SDK**, **LangChain**, **LangGraph**, **Claude
Agent SDK**. The runtime auto-detects the framework from the object you pass to
`runtime.run(...)`.

- [OpenAI Agents SDK](#openai-agents-sdk)
- [LangChain](#langchain)
- [LangGraph](#langgraph)
- [Claude Agent SDK](#claude-agent-sdk)

## OpenAI Agents SDK

Two ways. Either keep your existing `agents.Agent` and swap the runner, or use the
SDK's `Runner` with a native `Agent`.

### Drop-in `Runner`

Change one import — `from conductor.ai import Runner` instead of `from agents import
Runner` — and run your existing OpenAI-Agents agent on Conductor Agent:

```python
from conductor.ai import Runner            # the one line that changes
from agents import Agent, function_tool

@function_tool
def get_weather(city: str) -> str:
    return f"72F and sunny in {city}"

agent = Agent(
    name="weather_assistant",
    model="gpt-4o",
    tools=[get_weather],
    instructions="You are a helpful assistant.",
)

result = Runner.run_sync(agent, "What's the weather in NYC?")
print(result.final_output)
```

`Runner` methods (all classmethods, accept an OpenAI-Agents `Agent` or a native
`Agent`):

- `Runner.run_sync(starting_agent, input, *, context=None, max_turns=10, **kwargs) -> RunResult`
- `await Runner.run(starting_agent, input, *, context=None, max_turns=10, **kwargs) -> RunResult`
- `await Runner.run_streamed(starting_agent, input, *, context=None, max_turns=10, **kwargs) -> AsyncAgentStream`

`RunResult` exposes `.final_output` and `.execution_id`. (`context` is accepted for
compatibility and ignored.)

```python
import asyncio
from conductor.ai import Runner
from agents import Agent

agent = Agent(name="Assistant", instructions="You only respond in haikus.")
result = asyncio.run(Runner.run(agent, "Tell me about recursion."))
print(result.final_output)
```

`from conductor.ai import function_tool` is an alias of `@tool` for source compatibility.

## LangChain

Build a LangChain agent, then hand it to `runtime.run(...)`:

```python
from conductor.ai.agents import AgentRuntime
from langchain.agents import create_agent
from langchain_core.tools import tool as lc_tool

@lc_tool
def check_token() -> str:
    """Check a token."""
    return "available"

agent = create_agent("openai:gpt-4o", tools=[check_token],
                     system_prompt="You are a helpful assistant.")

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Is the token set?", credentials=["GITHUB_TOKEN"])
    result.print_result()
```

Conductor Agent also provides a thin wrapper, `conductor.ai.agents.langchain.create_agent`,
that captures the model, tools, and system prompt up front so they compile to native
server-side model + tool tasks (rather than running the whole agent in one opaque
worker).

## LangGraph

Pass a compiled graph (e.g. from `create_react_agent` or your own
`StateGraph().compile()`) to `runtime.run(...)`:

```python
import math
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from conductor.ai.agents import AgentRuntime

@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi}))

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
graph = create_react_agent(llm, tools=[calculate], name="math_agent")

with AgentRuntime() as runtime:
    result = runtime.run(graph, "What is sqrt(256) + 2**10?")
    result.print_result()
```

The bridge tries, in order, full extraction (model + `ToolNode` tools), then a
graph-structure compilation (nodes/edges become tasks), then passthrough. To mark a
node as requiring human input, decorate it with `human_task`:

```python
from conductor.ai.agents.frameworks.langgraph import human_task

@human_task(prompt="Review and approve before continuing.")
def approval_node(state): ...
```

## Claude Agent SDK

Run a Claude Agent SDK / Claude Code agent. The simplest path is a native `Agent`
configured with `ClaudeCode`:

```python
from conductor.ai.agents import Agent, AgentRuntime, ClaudeCode

fixer = Agent(
    name="claude_code_fixer",
    model=ClaudeCode("sonnet",
                     permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
    credentials=["GITHUB_TOKEN"],
    instructions="You are a senior developer fixing a GitHub issue.",
    tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],   # built-in string tools only
    max_turns=50,
)

with AgentRuntime() as rt:
    result = rt.run(fixer, "Pick an open issue and open a PR.", timeout=600000)
    result.print_result()
```

`ClaudeCode(model_name="", permission_mode=PermissionMode.ACCEPT_EDITS)`.
`permission_mode` is one of `DEFAULT`, `ACCEPT_EDITS`, `PLAN`, `BYPASS`. Claude Code
agents support the built-in string tools (`Read`, `Edit`, `Bash`, ...); custom `@tool`
functions are not yet supported there.

You can also bring `ClaudeCodeOptions` / a Claude Agent SDK agent directly; the bridge
runs the full `query()` in one durable worker with instrumentation hooks that stream
tool-use and lifecycle events back to Conductor Agent.
