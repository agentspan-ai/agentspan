<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="../../assets/logo-light.svg">
    <img src="../../assets/logo-light.svg" alt="Agentspan" width="400">
  </picture>
</p>

<h3 align="center">AI agents that don't die when your process does.</h3>

<p align="center">
  <a href="https://pypi.org/project/agentspan/"><img src="https://img.shields.io/pypi/v/agentspan?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/agentspan/"><img src="https://img.shields.io/pypi/dm/agentspan?color=blue" alt="Downloads"></a>
  <a href="https://github.com/agentspan-ai/agentspan/stargazers"><img src="https://img.shields.io/github/stars/agentspan-ai/agentspan?style=social" alt="Stars"></a>
  <a href="https://github.com/agentspan-ai/agentspan/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://discord.gg/agentspan"><img src="https://img.shields.io/discord/1234567890?label=Discord&logo=discord&color=5865F2" alt="Discord"></a>
  <a href="https://github.com/agentspan-ai/agentspan/actions"><img src="https://img.shields.io/github/actions/workflow/status/agentspan-ai/agentspan/ci.yml?label=CI" alt="CI"></a>
</p>

<p align="center">
  <a href="https://docs.agentspan.dev">Docs</a> &bull;
  <a href="#quickstart">Quickstart</a> &bull;
  <a href="#examples">52+ Examples</a> &bull;
  <a href="https://discord.gg/agentspan">Discord</a> &bull;
  <a href="../../docs/python-sdk/api-reference.md">API Reference</a>
</p>

---

**Agentspan** is a distributed, durable runtime for running AI agents that survive crashes, scale across machines, and pause for human approval for days — not minutes.

Every other agent SDK runs agents in-memory. When the process dies, the agent dies. Agentspan compiles your agents to durable executions that execute on a server, giving you reliability, observability, and distributed scaling out of the box.

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"

agent = Agent(name="weatherbot", model="openai/gpt-4o", tools=[get_weather])

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    result.print_result()
```

## Why Agentspan?

Other frameworks give you a Python library. Agentspan gives you a **production runtime**.

Your agent code compiles to a durable, server-side execution. The server manages execution, retries, scaling, and state — so your agents keep running even when your process doesn't.

| | CrewAI | LangChain | AutoGen | OpenAI Agents | **Agentspan**                                                          |
|---|---|---|---|---|------------------------------------------------------------------------|
| **Execution model** | In-memory | Checkpoints | In-memory | Client-side loop | **Durable executions**                                                 |
| **Crash recovery** | Manual replay from checkpoints | Resume from checkpointer (Postgres, Redis) | None (v0.4) | None (Temporal add-on available) | **Automatic — execution resumes exactly where it left off**            |
| **Tool scaling** | Single process | Single process (Platform for managed scaling) | Distributed runtime | Single process | **Distributed workers in any language (Python, Java, Go, etc.)**       |
| **Human approval** | Stdin-blocking (minutes) | `interrupt()` + checkpointer (days) | Stdin-blocking (minutes) | In-process | **Durable pause — approve from any process, any machine, days later**  |
| **Cross-process access** | None | Thread ID + checkpointer (rebuild graph) | None | `response_id` (continue only) | **Execution ID — status, approve, pause, resume, cancel from anywhere** |
| **Orchestration API** | Crew, Task, Agent, Flow | StateGraph, Node, Edge, ToolNode | AssistantAgent, GroupChat, Swarm, Team | Agent, Runner, Handoff | **One class: `Agent`**                                                 |
| **Pipeline syntax** | YAML + Python | Graph builder API | Nested class hierarchy | Handoff chains | **`agent_a >> agent_b >> agent_c`**                                    |
| **Guardrails** | Task guardrails | Middleware-based | Limited | Input, output, tool guardrails | **Custom, regex, LLM — 4 failure modes: retry, raise, fix, human**     |
| **Code execution** | Docker sandbox | Community packages | Docker, Jupyter | Hosted Code Interpreter | **4 built-in: local, Docker, Jupyter, serverless**                     |
| **MCP tools** | Manual config | Manual config | Manual config | Manual config | **Auto-discovered, server-side (no worker needed)**                    |
| **Observability** | OTel + CrewAI AMP | LangSmith + OTel | OTel + AutoGen Studio | Built-in traces | **OTel + Prometheus + visual execution UI + execution replay**         |

### What makes it different

1. **True durable execution** — Not checkpoints. Not client-side loops. Your agent compiles to a server-side execution that the Agentspan server executes independently of your process. Deploy new code, restart your machine, kill the process — the agent keeps running. When it finishes, poll for the result from anywhere. This is the same execution model that powers mission-critical systems at scale.

2. **Cross-process agent access** — Every running agent has an execution ID. Any process, on any machine, can use that ID to check status, stream events, approve or reject tool calls, pause, resume, or cancel the agent. No graph rebuilding, no checkpointer setup — just the ID and a runtime connection. LangGraph requires re-instantiating the graph and checkpointer; CrewAI and AutoGen have no cross-process access at all.

3. **Distributed workers in any language** — Tools don't run inside your agent process. They execute as distributed tasks that workers pick up. Write workers in Python, Java, Go, or any language. Scale each tool independently. Load-balance automatically. Your agent process just submits work — the server and workers handle the rest.

4. **One primitive** — No `Crew`, `Task`, `StateGraph`, `Node`, or `AssistantAgent`. Everything is an `Agent`. Single agents, multi-agent teams, nested hierarchies — one class.

5. **The `>>` operator** — Compose pipelines with Python syntax: `researcher >> writer >> editor`. No YAML, no graph builders.

6. **Real human-in-the-loop** — `@tool(approval_required=True)` pauses the execution durably on the server. No process stays alive waiting. Approve from any machine, any process, days later.

7. **Production guardrails** — Custom functions, regex patterns, or LLM judges. Four failure modes: retry, raise, fix, or escalate to human. Guardrails are durable tasks, not post-processing — they survive execution restarts.

8. **Server-side tools** — HTTP endpoints and MCP servers execute as server-side tasks. No worker process needed. MCP tools are auto-discovered at compile time.

9. **Code execution sandboxes** — Local subprocess, Docker containers, Jupyter kernels, or serverless functions. Four options, built in.

10. **Full observability** — OpenTelemetry spans, Prometheus metrics, visual execution UI, execution history, and token/cost tracking — all built in.

11. **Framework agnostic** — Use Google ADK, Langchain, OpenAI, CrewAI etc to write agents, run on Agentspan's durable execution runtime.

## Quickstart

### Install

```bash
uv venv && source .venv/bin/activate
uv pip install agentspan
```

### Start the Server

The SDK auto-starts the server when needed, but you can also start it manually (recommended):

```bash
# Set the API key for your LLM provider:
export OPENAI_API_KEY=sk-...          # For OpenAI models (gpt-4o, gpt-4o-mini, etc.)
# export ANTHROPIC_API_KEY=sk-ant-... # For Anthropic models (claude-sonnet, etc.)
# export GOOGLE_API_KEY=...           # For Google models (gemini, etc.)

agentspan server start   # Start the Agentspan server
agentspan server stop    # Stop the server
agentspan server logs    # View server logs
```


<details><summary>Configure remote Agentspan server connection</summary>

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
```

Or use a `.env` file:

```bash
cp .env.example .env
# Edit .env with your server URL and API keys
```

</details>

### Hello World

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="hello", model="openai/gpt-4o")

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Say hello and tell me a fun fact.")
    result.print_result()
```

### Add Tools

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "Sunny"}

@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression."""
    return {"result": eval(expression)}

agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    tools=[get_weather, calculate],
    instructions="You are a helpful assistant.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC? Also, what's 42 * 17?")
    result.print_result()
```

### Structured Output

```python
from pydantic import BaseModel
from agentspan.agents import Agent, AgentRuntime, tool

class WeatherReport(BaseModel):
    city: str
    temperature: float
    condition: str
    recommendation: str

@tool
def get_weather(city: str) -> dict:
    """Get weather data for a city."""
    return {"city": city, "temp_f": 72, "condition": "Sunny", "humidity": 45}

agent = Agent(name="reporter", model="openai/gpt-4o", tools=[get_weather], output_type=WeatherReport)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    report: WeatherReport = result.output  # Fully typed
    print(f"{report.city}: {report.temperature}F, {report.condition}")
```

### Multi-Agent Handoffs

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def check_balance(account_id: str) -> dict:
    """Check account balance."""
    return {"account_id": account_id, "balance": 5432.10}

billing = Agent(name="billing", model="openai/gpt-4o",
                instructions="Handle billing inquiries.", tools=[check_balance])
technical = Agent(name="technical", model="openai/gpt-4o",
                  instructions="Handle technical issues.")

support = Agent(
    name="support", model="openai/gpt-4o",
    instructions="Route customer requests to the right team.",
    agents=[billing, technical],
    strategy="handoff",
)

with AgentRuntime() as runtime:
    result = runtime.run(support, "What's the balance on account ACC-123?")
    result.print_result()
```

### Pipeline Composition

```python
from agentspan.agents import Agent, AgentRuntime

researcher = Agent(name="researcher", model="openai/gpt-4o",
                   instructions="Research the topic and provide key facts.")
writer = Agent(name="writer", model="openai/gpt-4o",
               instructions="Write an engaging article from the research.")
editor = Agent(name="editor", model="openai/gpt-4o",
               instructions="Polish the article for publication.")

pipeline = researcher >> writer >> editor

with AgentRuntime() as runtime:
    result = runtime.run(pipeline, "AI agents in software development")
    result.print_result()
```

### Parallel Agents

```python
from agentspan.agents import Agent, AgentRuntime

market = Agent(name="market", model="openai/gpt-4o",
               instructions="Analyze market size, growth, key players.")
risk = Agent(name="risk", model="openai/gpt-4o",
             instructions="Analyze regulatory, technical, competitive risks.")

analysis = Agent(name="analysis", model="openai/gpt-4o",
                 agents=[market, risk], strategy="parallel")

with AgentRuntime() as runtime:
    result = runtime.run(analysis, "Launching an AI healthcare tool in the US")
    result.print_result()
```

### Human-in-the-Loop (Durable)

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer funds. Requires human approval."""
    return {"status": "completed", "amount": amount}

agent = Agent(name="banker", model="openai/gpt-4o", tools=[transfer_funds])

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Transfer $5000 from checking to savings")
    # Execution pauses at transfer_funds...

    # Days later, from any process, any machine:
    status = handle.get_status()
    if status.is_waiting:
        handle.approve()   # Or: handle.reject("Amount too high")
```

### Guardrails

```python
from agentspan.agents import Agent, AgentRuntime, Guardrail, GuardrailResult, OnFail, guardrail

@guardrail
def word_limit(content: str) -> GuardrailResult:
    """Keep responses concise."""
    if len(content.split()) > 500:
        return GuardrailResult(passed=False, message="Too long. Be more concise.")
    return GuardrailResult(passed=True)

agent = Agent(
    name="concise_bot", model="openai/gpt-4o",
    guardrails=[Guardrail(word_limit, on_fail=OnFail.RETRY)],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Explain quantum computing.")
    result.print_result()
```

### Streaming

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="writer", model="openai/gpt-4o")

with AgentRuntime() as runtime:
    for event in runtime.stream(agent, "Write a haiku about Python"):
        match event.type:
            case "tool_call":       print(f"Calling {event.tool_name}...")
            case "thinking":        print(f"Thinking: {event.content}")
            case "guardrail_pass":  print(f"Guardrail passed: {event.guardrail_name}")
            case "guardrail_fail":  print(f"Guardrail failed: {event.guardrail_name}")
            case "done":            print(f"\n{event.output}")
```

### Server-Side Tools (No Workers Needed)

```python
from agentspan.agents import Agent, AgentRuntime, http_tool, mcp_tool

weather_api = http_tool(
    name="get_weather", description="Get weather for a city",
    url="https://api.weather.com/v1/current", method="GET",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
)

github = mcp_tool(server_url="http://localhost:6767/mcp")  # Auto-discovered

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[weather_api, github])

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    result.print_result()
```

### Code Execution

```python
from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.code_executor import DockerCodeExecutor

executor = DockerCodeExecutor(image="python:3.12-slim", timeout=30)
agent = Agent(
    name="coder", model="openai/gpt-4o",
    tools=[executor.as_tool()],
    instructions="Write and execute Python code to solve problems.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Calculate the first 20 Fibonacci numbers.")
    result.print_result()
```

### Shared State (Tool Context)

```python
from agentspan.agents import Agent, AgentRuntime, tool, ToolContext

@tool
def add_item(item: str, context: ToolContext) -> str:
    """Add an item to the shared list."""
    items = context.state.get("items", [])
    items.append(item)
    context.state["items"] = items
    return f"Added '{item}'. List now has {len(items)} items."

@tool
def get_items(context: ToolContext) -> str:
    """Get all items from the shared list."""
    items = context.state.get("items", [])
    return f"Items: {', '.join(items)}" if items else "No items yet."

agent = Agent(
    name="list_manager", model="openai/gpt-4o",
    tools=[add_item, get_items],
    instructions="Manage a shared list of items.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Add apples, bananas, and cherries, then show the list.")
    result.print_result()
```

### Agent Lifecycle Callbacks

Hook into agent, model, and tool lifecycle events with `CallbackHandler` classes. Multiple handlers chain per-position in list order — each one handles a single concern:

```python
import time
from agentspan.agents import Agent, AgentRuntime, CallbackHandler

class TimingHandler(CallbackHandler):
    def on_agent_start(self, **kwargs):
        self.t0 = time.time()
    def on_agent_end(self, **kwargs):
        print(f"Took {time.time() - self.t0:.2f}s")

class LoggingHandler(CallbackHandler):
    def on_model_start(self, *, messages=None, **kwargs):
        print(f"Sending {len(messages or [])} messages")
    def on_model_end(self, *, llm_result=None, **kwargs):
        print(f"LLM responded: {(llm_result or '')[:80]}")

agent = Agent(
    name="my_agent",
    model="openai/gpt-4o-mini",
    instructions="You are a helpful assistant.",
    callbacks=[TimingHandler(), LoggingHandler()],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Hello!")
    result.print_result()
```

Six hook positions: `on_agent_start`, `on_agent_end`, `on_model_start`, `on_model_end`, `on_tool_start`, `on_tool_end`.

Execution order: `on_agent_start` → (`on_model_start` → LLM → `on_model_end`)* → `on_agent_end`

## Multi-Agent Strategies

| Strategy | Description |
|---|---|
| `handoff` (default) | LLM chooses which sub-agent handles the request |
| `sequential` | Sub-agents run in order, output feeds forward (`>>` operator) |
| `parallel` | All sub-agents run concurrently, results aggregated |
| `router` | Router agent or function selects the sub-agent |
| `round_robin` | Agents take turns in a fixed rotation |
| `swarm` | Condition-based handoffs between agents |
| `random` | Random sub-agent selection each turn |

## Examples

Runnable examples covering every feature:

| Example | Description |
|---|---|
| [`01_basic_agent.py`](examples/01_basic_agent.py) | Hello world |
| [`02_tools.py`](examples/02_tools.py) | Multiple tools with approval |
| [`02a_simple_tools.py`](examples/02a_simple_tools.py) | Two tools, LLM picks the right one |
| [`02b_multi_step_tools.py`](examples/02b_multi_step_tools.py) | Chained lookups and calculations |
| [`03_structured_output.py`](examples/03_structured_output.py) | Pydantic output types |
| [`04_http_and_mcp_tools.py`](examples/04_http_and_mcp_tools.py) | Server-side HTTP and MCP tools |
| [`04_mcp_weather.py`](examples/04_mcp_weather.py) | MCP server tools (live weather) |
| [`05_handoffs.py`](examples/05_handoffs.py) | Agent delegation |
| [`06_sequential_pipeline.py`](examples/06_sequential_pipeline.py) | `agent >> agent >> agent` |
| [`07_parallel_agents.py`](examples/07_parallel_agents.py) | Fan-out / fan-in |
| [`08_router_agent.py`](examples/08_router_agent.py) | LLM routing to specialists |
| [`09_human_in_the_loop.py`](examples/09_human_in_the_loop.py) | Approval patterns |
| [`09b_hitl_with_feedback.py`](examples/09b_hitl_with_feedback.py) | Custom feedback (respond API) |
| [`09c_hitl_streaming.py`](examples/09c_hitl_streaming.py) | Streaming + HITL approval |
| [`10_guardrails.py`](examples/10_guardrails.py) | Output validation + retry |
| [`11_streaming.py`](examples/11_streaming.py) | Real-time events |
| [`12_long_running.py`](examples/12_long_running.py) | Fire-and-forget with polling |
| [`13_hierarchical_agents.py`](examples/13_hierarchical_agents.py) | Nested agent teams |
| [`14_existing_workers.py`](examples/14_existing_workers.py) | Existing workers as tools |
| [`15_agent_discussion.py`](examples/15_agent_discussion.py) | Round-robin debate |
| [`16_random_strategy.py`](examples/16_random_strategy.py) | Random agent selection |
| [`17_swarm_orchestration.py`](examples/17_swarm_orchestration.py) | Swarm with handoff conditions |
| [`18_manual_selection.py`](examples/18_manual_selection.py) | Human picks which agent speaks |
| [`19_composable_termination.py`](examples/19_composable_termination.py) | Composable termination conditions |
| [`20_constrained_transitions.py`](examples/20_constrained_transitions.py) | Restricted agent transitions |
| [`21_regex_guardrails.py`](examples/21_regex_guardrails.py) | RegexGuardrail (block/allow) |
| [`22_llm_guardrails.py`](examples/22_llm_guardrails.py) | LLMGuardrail (AI judge) |
| [`23_token_tracking.py`](examples/23_token_tracking.py) | Token usage and cost tracking |
| [`24_code_execution.py`](examples/24_code_execution.py) | Code execution sandboxes |
| [`25_semantic_memory.py`](examples/25_semantic_memory.py) | Long-term memory with retrieval |
| [`26_opentelemetry_tracing.py`](examples/26_opentelemetry_tracing.py) | OpenTelemetry spans |
| [`27_user_proxy_agent.py`](examples/27_user_proxy_agent.py) | Interactive conversations |
| [`28_gpt_assistant_agent.py`](examples/28_gpt_assistant_agent.py) | OpenAI Assistants API wrapper |
| [`29_agent_introductions.py`](examples/29_agent_introductions.py) | Agents introduce themselves |
| [`30_multimodal_agent.py`](examples/30_multimodal_agent.py) | Vision model analysis |
| [`31_tool_guardrails.py`](examples/31_tool_guardrails.py) | Pre-execution tool validation |
| [`32_human_guardrail.py`](examples/32_human_guardrail.py) | Human review on guardrail failure |
| [`33_external_workers.py`](examples/33_external_workers.py) | Workers in other services |
| [`33_single_turn_tool.py`](examples/33_single_turn_tool.py) | Single-turn tool call |
| [`34_prompt_templates.py`](examples/34_prompt_templates.py) | Server-side prompt templates |
| [`35_standalone_guardrails.py`](examples/35_standalone_guardrails.py) | Guardrails without agents |
| [`36_simple_agent_guardrails.py`](examples/36_simple_agent_guardrails.py) | Guardrails on simple agents |
| [`37_fix_guardrail.py`](examples/37_fix_guardrail.py) | Auto-correct with on_fail="fix" |
| [`38_tech_trends.py`](examples/38_tech_trends.py) | Tech trends research |
| [`39_local_code_execution.py`](examples/39_local_code_execution.py) | Local code sandbox |
| [`39a_docker_code_execution.py`](examples/39a_docker_code_execution.py) | Docker-sandboxed execution |
| [`39b_jupyter_code_execution.py`](examples/39b_jupyter_code_execution.py) | Jupyter kernel execution |
| [`39c_serverless_code_execution.py`](examples/39c_serverless_code_execution.py) | Serverless execution |
| [`40_media_generation_agent.py`](examples/40_media_generation_agent.py) | Image/audio/video generation |
| [`41_sequential_pipeline_tools.py`](examples/41_sequential_pipeline_tools.py) | Pipeline with per-stage tools |
| [`42_security_testing.py`](examples/42_security_testing.py) | Security testing pipeline |
| [`43_data_security_pipeline.py`](examples/43_data_security_pipeline.py) | Data redaction pipeline |
| [`44_safety_guardrails.py`](examples/44_safety_guardrails.py) | PII detection and sanitization |
| [`45_agent_tool.py`](examples/45_agent_tool.py) | Agent as a callable tool |
| [`46_transfer_control.py`](examples/46_transfer_control.py) | Restricted handoff transitions |
| [`47_callbacks.py`](examples/47_callbacks.py) | Lifecycle hooks |
| [`48_planner.py`](examples/48_planner.py) | Planning before execution |
| [`49_include_contents.py`](examples/49_include_contents.py) | Context control for sub-agents |
| [`50_thinking_config.py`](examples/50_thinking_config.py) | Extended reasoning |
| [`51_shared_state.py`](examples/51_shared_state.py) | Shared state via ToolContext |
| [`52_nested_strategies.py`](examples/52_nested_strategies.py) | Nested parallel + sequential |
| [`53_agent_lifecycle_callbacks.py`](examples/53_agent_lifecycle_callbacks.py) | Agent-level before/after hooks |

### Google ADK Compatibility

Drop-in compatibility with the [Google ADK](https://github.com/google/adk-python) API, backed by durable execution. [32 examples included](examples/adk/).

```python
from google.adk.agents import Agent, SequentialAgent

researcher = Agent(name="researcher", model="gemini-2.0-flash",
                   instruction="Research the topic.", tools=[search])
writer = Agent(name="writer", model="gemini-2.0-flash",
               instruction="Write an article from the research.")

pipeline = SequentialAgent(name="pipeline", sub_agents=[researcher, writer])
```

## Community

We're building Agentspan in the open and would love your help.

- **[Discord](https://discord.gg/agentspan)** — Ask questions, share what you're building, get help
- **[GitHub Issues](https://github.com/agentspan-ai/agentspan/issues)** — Bug reports and feature requests
- **[Contributing Guide](CONTRIBUTING.md)** — How to contribute code, docs, and examples

### Contributing

```bash
git clone https://github.com/agentspan-ai/agentspan.git
cd agentspan/sdk/python
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

We welcome PRs of all sizes — from typo fixes to new examples to core features.

### Spread the Word

If Agentspan is useful to you, help others find it:

- [Star this repo](https://github.com/agentspan-ai/agentspan) — it helps more than you think
- [Share on LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https://github.com/agentspan-ai/agentspan) — tell your network
- [Share on X/Twitter](https://twitter.com/intent/tweet?text=Agentspan%20%E2%80%94%20AI%20agents%20that%20don%27t%20die%20when%20your%20process%20does.%20Durable%2C%20scalable%2C%20observable.&url=https://github.com/agentspan-ai/agentspan) — spread the word
- [Share on Reddit](https://www.reddit.com/submit?url=https://github.com/agentspan-ai/agentspan&title=Agentspan%20%E2%80%94%20AI%20agents%20that%20survive%20crashes%2C%20scale%20across%20machines%2C%20and%20pause%20for%20human%20approval%20for%20days) — post in r/MachineLearning or r/LocalLLaMA

## API Reference

See [API Reference](../../docs/python-sdk/api-reference.md) for the complete API reference and architecture guide.

## License

[MIT](LICENSE)
