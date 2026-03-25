<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img src="assets/logo-light.svg" alt="Agentspan" width="400">
  </picture>
</p>

<h3 align="center">AI agents that don't die when your process does.</h3>

<p align="center">
  <a href="https://pypi.org/project/agentspan/"><img src="https://img.shields.io/pypi/v/agentspan?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/agentspan/"><img src="https://img.shields.io/pypi/dm/agentspan?color=blue" alt="Downloads"></a>
  <a href="https://github.com/agentspan/agentspan/stargazers"><img src="https://img.shields.io/github/stars/agentspan/agentspan?style=social" alt="Stars"></a>
  <a href="https://github.com/agentspan/agentspan/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://discord.gg/agentspan"><img src="https://img.shields.io/discord/1234567890?label=Discord&logo=discord&color=5865F2" alt="Discord"></a>
  <a href="https://github.com/agentspan/agentspan/actions"><img src="https://img.shields.io/github/actions/workflow/status/agentspan/agentspan/ci.yml?label=CI" alt="CI"></a>
</p>

<p align="center">
  <a href="https://docs.agentspan.dev">Docs</a> &bull;
  <a href="#quickstart">Quickstart</a> &bull;
  <a href="#examples">180+ Examples</a> &bull;
  <a href="https://discord.gg/agentspan">Discord</a> &bull;
  <a href="docs/python-sdk/api-reference.md">API Reference</a>
</p>

---

**Agentspan** is a distributed, durable runtime for AI agents that survive crashes, scale across machines, and pause for human approval for days — not minutes.

## Quickstart (60 seconds)

```bash
# 1. Install
npm install -g @agentspan/agentspan          # installs the CLI
pip install agentspan                         # installs the Python SDK
export OPENAI_API_KEY=sk-...                  # or any supported provider

# 2. Start the server
agentspan server start                        # runs on localhost:8080 with UI
```

```python
# 3. Run your first agent (save as hello.py, run with: python hello.py)
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

That's it. The server auto-starts workers, compiles your agent to a durable workflow, and executes it. Open `http://localhost:8080` to see the visual workflow UI.

<details><summary>Alternative install methods</summary>

```bash
# CLI alternative (if you don't have npm)
curl -fsSL https://raw.githubusercontent.com/agentspan/agentspan/main/cli/install.sh | sh

# Python SDK with uv
uv pip install agentspan

# Verify setup
agentspan doctor
```

</details>

<details><summary>All supported LLM providers (15+)</summary>

| Provider | Env Var | Model Format |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `openai/gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/claude-sonnet-4-20250514` |
| Google Gemini | `GEMINI_API_KEY` | `google_gemini/gemini-pro` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` | `azure_openai/gpt-4o` |
| Google Vertex AI | `GOOGLE_CLOUD_PROJECT` | `google_vertex_ai/gemini-pro` |
| AWS Bedrock | `AWS_ACCESS_KEY_ID` | `aws_bedrock/anthropic.claude-v2` |
| Mistral | `MISTRAL_API_KEY` | `mistral/mistral-large` |
| Cohere | `COHERE_API_KEY` | `cohere/command-r-plus` |
| Groq | `GROQ_API_KEY` | `groq/llama-3-70b` |
| Perplexity | `PERPLEXITY_API_KEY` | `perplexity/sonar-medium` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/deepseek-chat` |
| Grok / xAI | `XAI_API_KEY` | `grok/grok-3` |
| HuggingFace | `HUGGINGFACE_API_KEY` | `hugging_face/meta-llama/Llama-3-70b` |
| Stability AI | `STABILITY_API_KEY` | `stabilityai/sd3.5-large` |
| Ollama (local) | `OLLAMA_HOST` | `ollama/llama3` |

</details>

---

## Why Agentspan?

Every other agent SDK runs agents in-memory. When the process dies, the agent dies. Agentspan compiles your agents to durable workflows that execute on a server — giving you reliability, observability, and distributed scaling out of the box.

| | CrewAI | LangChain | AutoGen | OpenAI Agents | **Agentspan** |
|---|---|---|---|---|---|
| **Execution model** | In-memory | Checkpoints | In-memory | Client-side loop | **Server-side workflows** |
| **Crash recovery** | Manual replay | Checkpointer (Postgres) | None | None | **Automatic resume** |
| **Tool scaling** | Single process | Single process | Distributed | Single process | **Distributed workers (any language)** |
| **Human approval** | Stdin-blocking | `interrupt()` + checkpointer | Stdin-blocking | In-process | **Durable pause (days, any machine)** |
| **Orchestration API** | Crew, Task, Agent, Flow | StateGraph, Node, Edge | AssistantAgent, GroupChat | Agent, Runner, Handoff | **One class: `Agent`** |
| **Pipeline syntax** | YAML + Python | Graph builder API | Nested class hierarchy | Handoff chains | **`a >> b >> c`** |
| **Guardrails** | Task guardrails | Middleware-based | Limited | Input/output/tool | **Custom, regex, LLM — 4 failure modes** |
| **Code execution** | Docker sandbox | Community packages | Docker, Jupyter | Hosted interpreter | **4 built-in sandboxes** |
| **MCP tools** | Manual config | Manual config | Manual config | Manual config | **Auto-discovered, server-side** |

<details><summary>What makes it different (detailed)</summary>

1. **True durable execution** — Your agent compiles to a server-side workflow. Kill the process — the agent keeps running. Poll for results from anywhere.

2. **Cross-process agent access** — Every agent has a workflow ID. Check status, stream events, approve tool calls, pause, resume, or cancel from any process, any machine.

3. **Distributed workers in any language** — Tools execute as distributed tasks. Write workers in Python, Java, Go, or any language. Scale each tool independently.

4. **One primitive** — Everything is an `Agent`. Single agents, multi-agent teams, nested hierarchies — one class.

5. **Real human-in-the-loop** — `@tool(approval_required=True)` pauses the workflow durably. Approve days later, from any machine.

6. **Production guardrails** — Custom functions, regex, or LLM judges. Four failure modes: retry, raise, fix, or human escalation.

7. **Server-side tools** — HTTP endpoints and MCP servers execute as server-side tasks. No worker needed. MCP auto-discovered at compile time.

8. **Full observability** — OpenTelemetry, Prometheus, visual workflow UI, execution history, token/cost tracking.

9. **Framework compatible** — Works with Google ADK, OpenAI Agents SDK, LangChain, and LangGraph. [180+ examples](sdk/python/examples/).

</details>

## Code Examples

### Agent with Tools

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
```

### Credential Management

Store API keys and secrets once on the server. Tools resolve them automatically at runtime — no `.env` files, no hardcoded keys, no secrets in git.

**Step 1: Store credentials on the server**

```bash
agentspan credential store GITHUB_TOKEN ghp_xxxxxxxxxxxx
agentspan credential store SEARCH_API_KEY xxx-your-key
```

Credentials are encrypted at rest (AES-256-GCM). List them with `agentspan credential list`.

**Step 2: Declare which credentials a tool needs**

```python
from agentspan.agents import Agent, AgentRuntime, tool, get_credential

# Default: tool runs in isolated subprocess with credentials as env vars
@tool(credentials=["GITHUB_TOKEN"])
def list_repos(username: str) -> dict:
    """List GitHub repos."""
    import os
    token = os.environ["GITHUB_TOKEN"]  # Auto-injected by the runtime
    return {"repos": ["repo1", "repo2"]}

# Alternative: access credentials in-process (no subprocess)
@tool(isolated=False, credentials=["SEARCH_API_KEY"])
def search(query: str) -> dict:
    """Search using API key."""
    key = get_credential("SEARCH_API_KEY")  # Resolve from server at runtime
    return {"results": ["result1"]}
```

**Step 3: Run — credentials resolve automatically**

```python
agent = Agent(
    name="github_helper",
    model="openai/gpt-4o",
    tools=[list_repos, search],
    credentials=["GITHUB_TOKEN"],  # Agent-level credentials (shared with all tools)
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "List my GitHub repos and search for AI papers")
    result.print_result()
```

**Credentials work with every tool type:**

```python
from agentspan.agents import http_tool, mcp_tool

# HTTP tools: server substitutes ${NAME} in headers at runtime
api = http_tool(
    name="weather_api", description="Get weather data",
    url="https://api.weather.com/v1/current",
    headers={"Authorization": "Bearer ${WEATHER_KEY}"},
    credentials=["WEATHER_KEY"],
)

# MCP tools: credentials passed to MCP server connection
github = mcp_tool(server_url="http://localhost:3001/mcp", credentials=["GITHUB_TOKEN"])
```

No credentials leave the server unencrypted. Workers resolve them via scoped execution tokens that expire with the workflow. See the [11 credential examples](sdk/python/examples/) (`16_*.py` through `16k_*.py`) for every mode: isolated subprocess, in-process, CLI tools, HTTP headers, MCP, and framework passthrough.

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
from agentspan.agents import Agent, AgentRuntime, api_tool, http_tool, mcp_tool

# Point to any OpenAPI/Swagger spec — all endpoints auto-discovered
stripe = api_tool(
    url="https://api.stripe.com/openapi.json",
    headers={"Authorization": "Bearer ${STRIPE_KEY}"},
    credentials=["STRIPE_KEY"],
    max_tools=20,  # LLM auto-filters 300+ ops to top 20 most relevant
)

# Single HTTP endpoint (manual definition)
weather_api = http_tool(
    name="get_weather", description="Get weather for a city",
    url="https://api.weather.com/v1/current", method="GET",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
)

# MCP server tools (auto-discovered)
github = mcp_tool(server_url="http://localhost:8080/mcp")

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[stripe, weather_api, github])

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Create a Stripe customer for alice@example.com")
    result.print_result()
```

Three ways to connect APIs — all server-side, no workers needed:
- **`api_tool()`** — point to an OpenAPI/Swagger/Postman spec, all endpoints auto-discovered
- **`http_tool()`** — define a single HTTP endpoint manually
- **`mcp_tool()`** — connect to an MCP server, tools auto-discovered

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
| `manual` | Human selects which agent speaks each turn |

## Examples

180+ runnable examples covering every feature across 5 frameworks:

| Example | Description |
|---|---|
| [`01_basic_agent.py`](sdk/python/examples/01_basic_agent.py) | Hello world |
| [`02_tools.py`](sdk/python/examples/02_tools.py) | Multiple tools with approval |
| [`02a_simple_tools.py`](sdk/python/examples/02a_simple_tools.py) | Two tools, LLM picks the right one |
| [`02b_multi_step_tools.py`](sdk/python/examples/02b_multi_step_tools.py) | Chained lookups and calculations |
| [`03_structured_output.py`](sdk/python/examples/03_structured_output.py) | Pydantic output types |
| [`04_http_and_mcp_tools.py`](sdk/python/examples/04_http_and_mcp_tools.py) | Server-side HTTP and MCP tools |
| [`04_mcp_weather.py`](sdk/python/examples/04_mcp_weather.py) | MCP server tools (live weather) |
| [`05_handoffs.py`](sdk/python/examples/05_handoffs.py) | Agent delegation |
| [`06_sequential_pipeline.py`](sdk/python/examples/06_sequential_pipeline.py) | `agent >> agent >> agent` |
| [`07_parallel_agents.py`](sdk/python/examples/07_parallel_agents.py) | Fan-out / fan-in |
| [`08_router_agent.py`](sdk/python/examples/08_router_agent.py) | LLM routing to specialists |
| [`09_human_in_the_loop.py`](sdk/python/examples/09_human_in_the_loop.py) | Approval workflows |
| [`09b_hitl_with_feedback.py`](sdk/python/examples/09b_hitl_with_feedback.py) | Custom feedback (respond API) |
| [`09c_hitl_streaming.py`](sdk/python/examples/09c_hitl_streaming.py) | Streaming + HITL approval |
| [`10_guardrails.py`](sdk/python/examples/10_guardrails.py) | Output validation + retry |
| [`11_streaming.py`](sdk/python/examples/11_streaming.py) | Real-time events |
| [`12_long_running.py`](sdk/python/examples/12_long_running.py) | Fire-and-forget with polling |
| [`13_hierarchical_agents.py`](sdk/python/examples/13_hierarchical_agents.py) | Nested agent teams |
| [`14_existing_workers.py`](sdk/python/examples/14_existing_workers.py) | Existing workers as tools |
| [`15_agent_discussion.py`](sdk/python/examples/15_agent_discussion.py) | Round-robin debate |
| [`16_random_strategy.py`](sdk/python/examples/16_random_strategy.py) | Random agent selection |
| [`17_swarm_orchestration.py`](sdk/python/examples/17_swarm_orchestration.py) | Swarm with handoff conditions |
| [`18_manual_selection.py`](sdk/python/examples/18_manual_selection.py) | Human picks which agent speaks |
| [`19_composable_termination.py`](sdk/python/examples/19_composable_termination.py) | Composable termination conditions |
| [`20_constrained_transitions.py`](sdk/python/examples/20_constrained_transitions.py) | Restricted agent transitions |
| [`21_regex_guardrails.py`](sdk/python/examples/21_regex_guardrails.py) | RegexGuardrail (block/allow) |
| [`22_llm_guardrails.py`](sdk/python/examples/22_llm_guardrails.py) | LLMGuardrail (AI judge) |
| [`23_token_tracking.py`](sdk/python/examples/23_token_tracking.py) | Token usage and cost tracking |
| [`24_code_execution.py`](sdk/python/examples/24_code_execution.py) | Code execution sandboxes |
| [`25_semantic_memory.py`](sdk/python/examples/25_semantic_memory.py) | Long-term memory with retrieval |
| [`26_opentelemetry_tracing.py`](sdk/python/examples/26_opentelemetry_tracing.py) | OpenTelemetry spans |
| [`27_user_proxy_agent.py`](sdk/python/examples/27_user_proxy_agent.py) | Interactive conversations |
| [`28_gpt_assistant_agent.py`](sdk/python/examples/28_gpt_assistant_agent.py) | OpenAI Assistants API wrapper |
| [`29_agent_introductions.py`](sdk/python/examples/29_agent_introductions.py) | Agents introduce themselves |
| [`30_multimodal_agent.py`](sdk/python/examples/30_multimodal_agent.py) | Vision model analysis |
| [`31_tool_guardrails.py`](sdk/python/examples/31_tool_guardrails.py) | Pre-execution tool validation |
| [`32_human_guardrail.py`](sdk/python/examples/32_human_guardrail.py) | Human review on guardrail failure |
| [`33_external_workers.py`](sdk/python/examples/33_external_workers.py) | Workers in other services |
| [`33_single_turn_tool.py`](sdk/python/examples/33_single_turn_tool.py) | Single-turn tool call |
| [`34_prompt_templates.py`](sdk/python/examples/34_prompt_templates.py) | Server-side prompt templates |
| [`35_standalone_guardrails.py`](sdk/python/examples/35_standalone_guardrails.py) | Guardrails without agents |
| [`36_simple_agent_guardrails.py`](sdk/python/examples/36_simple_agent_guardrails.py) | Guardrails on simple agents |
| [`37_fix_guardrail.py`](sdk/python/examples/37_fix_guardrail.py) | Auto-correct with on_fail="fix" |
| [`38_tech_trends.py`](sdk/python/examples/38_tech_trends.py) | Tech trends research |
| [`39_local_code_execution.py`](sdk/python/examples/39_local_code_execution.py) | Local code sandbox |
| [`39a_docker_code_execution.py`](sdk/python/examples/39a_docker_code_execution.py) | Docker-sandboxed execution |
| [`39b_jupyter_code_execution.py`](sdk/python/examples/39b_jupyter_code_execution.py) | Jupyter kernel execution |
| [`39c_serverless_code_execution.py`](sdk/python/examples/39c_serverless_code_execution.py) | Serverless execution |
| [`40_media_generation_agent.py`](sdk/python/examples/40_media_generation_agent.py) | Image/audio/video generation |
| [`41_sequential_pipeline_tools.py`](sdk/python/examples/41_sequential_pipeline_tools.py) | Pipeline with per-stage tools |
| [`42_security_testing.py`](sdk/python/examples/42_security_testing.py) | Security testing pipeline |
| [`43_data_security_pipeline.py`](sdk/python/examples/43_data_security_pipeline.py) | Data redaction pipeline |
| [`44_safety_guardrails.py`](sdk/python/examples/44_safety_guardrails.py) | PII detection and sanitization |
| [`45_agent_tool.py`](sdk/python/examples/45_agent_tool.py) | Agent as a callable tool |
| [`46_transfer_control.py`](sdk/python/examples/46_transfer_control.py) | Restricted handoff transitions |
| [`47_callbacks.py`](sdk/python/examples/47_callbacks.py) | Lifecycle hooks |
| [`48_planner.py`](sdk/python/examples/48_planner.py) | Planning before execution |
| [`49_include_contents.py`](sdk/python/examples/49_include_contents.py) | Context control for sub-agents |
| [`50_thinking_config.py`](sdk/python/examples/50_thinking_config.py) | Extended reasoning |
| [`51_shared_state.py`](sdk/python/examples/51_shared_state.py) | Shared state via ToolContext |
| [`52_nested_strategies.py`](sdk/python/examples/52_nested_strategies.py) | Nested parallel + sequential |
| [`53_agent_lifecycle_callbacks.py`](sdk/python/examples/53_agent_lifecycle_callbacks.py) | Agent-level before/after hooks |
| [`54_software_bug_assistant.py`](sdk/python/examples/54_software_bug_assistant.py) | Software debugging agent |
| [`55_ml_engineering.py`](sdk/python/examples/55_ml_engineering.py) | ML engineering assistant |
| [`56_rag_agent.py`](sdk/python/examples/56_rag_agent.py) | Retrieval-augmented generation |
| [`57_plan_dry_run.py`](sdk/python/examples/57_plan_dry_run.py) | Plan execution preview |
| [`58_scatter_gather.py`](sdk/python/examples/58_scatter_gather.py) | Massive parallel map-reduce |
| [`59_coding_agent.py`](sdk/python/examples/59_coding_agent.py) | Code generation agent |
| [`60_github_coding_agent.py`](sdk/python/examples/60_github_coding_agent.py) | GitHub integration for coding |
| [`61_github_coding_agent_chained.py`](sdk/python/examples/61_github_coding_agent_chained.py) | Chained GitHub operations |
| [`62_cli_tool_guardrails.py`](sdk/python/examples/62_cli_tool_guardrails.py) | CLI tool input validation |
| [`63_deploy.py`](sdk/python/examples/63_deploy.py) | Agent deployment |
| [`64_swarm_with_tools.py`](sdk/python/examples/64_swarm_with_tools.py) | Swarm + tool orchestration |
| [`65_parallel_with_tools.py`](sdk/python/examples/65_parallel_with_tools.py) | Parallel agents with tools |
| [`66_handoff_to_parallel.py`](sdk/python/examples/66_handoff_to_parallel.py) | Handoff to parallel execution |
| [`67_router_to_sequential.py`](sdk/python/examples/67_router_to_sequential.py) | Router to sequential pipeline |
| [`68_context_condensation.py`](sdk/python/examples/68_context_condensation.py) | Auto-condense long conversations |
| [`70_ce_support_agent.py`](sdk/python/examples/70_ce_support_agent.py) | Full support agent with Zendesk, JIRA, HubSpot |
| [`71_api_tool.py`](sdk/python/examples/71_api_tool.py) | Auto-discover tools from OpenAPI/Swagger/Postman |

**Framework Examples:**

| Framework | Count | Location |
|---|---|---|
| [OpenAI Agents SDK](sdk/python/examples/openai/) | 10 examples | Handoffs, guardrails, streaming, multi-model |
| [Google ADK](sdk/python/examples/adk/) | 35 examples | Full ADK compatibility, all agent types |
| [LangChain](sdk/python/examples/langchain/) | 25 examples | ReAct, memory, document analysis |
| [LangGraph](sdk/python/examples/langgraph/) | 44 examples | StateGraph, human-in-the-loop, subgraphs |

### Google ADK Compatibility

Drop-in compatibility with the [Google ADK](https://github.com/google/adk-python) API, backed by durable execution. [32 examples included](sdk/python/examples/adk/).

```python
from google.adk.agents import Agent, SequentialAgent

researcher = Agent(name="researcher", model="gemini-2.0-flash",
                   instruction="Research the topic.", tools=[search])
writer = Agent(name="writer", model="gemini-2.0-flash",
               instruction="Write an article from the research.")

pipeline = SequentialAgent(name="pipeline", sub_agents=[researcher, writer])
```

## Deployment

### Development (SQLite — zero setup)

The default setup uses SQLite with WAL mode. No external database needed.

```bash
agentspan server start
```

Data is stored in `agent-runtime.db` in the working directory.

### Production (PostgreSQL)

For production workloads, use PostgreSQL for durability and concurrent access.

**1. Start PostgreSQL with Docker Compose:**

```bash
cd deployment/docker-compose
cp .env.example .env
docker compose up -d postgres
```

This starts PostgreSQL 16 on port 5432 with:
- User: `agentspan` (default)
- Password: `changeme` (default)
- Database: `agentspan` (default)

**2. Start the server with the Postgres profile:**

```bash
SPRING_PROFILES_ACTIVE=postgres agentspan server start
```

Or configure the database connection directly:

```bash
export SPRING_DATASOURCE_URL=jdbc:postgresql://your-host:5432/conductor
export SPRING_DATASOURCE_USERNAME=your_user
export SPRING_DATASOURCE_PASSWORD=your_password
export SPRING_PROFILES_ACTIVE=postgres
agentspan server start
```

### Docker Deployment

Run the Agentspan server and PostgreSQL together using the deployment Compose stack:

```bash
cd deployment/docker-compose
cp .env.example .env
docker compose up -d
```

Compose files:
- `deployment/docker-compose/compose.yaml`
- `deployment/docker-compose/.env.example`
- `deployment/docker-compose/README.md`

### Configuration Reference

The server auto-enables LLM providers when their API key is set. No manual integration setup needed.

| Setting | Env Var | Default |
|---|---|---|
| Server port | `SERVER_PORT` | `8080` |
| Database backend | `SPRING_PROFILES_ACTIVE` | `default` (SQLite) |
| SQLite path | `SPRING_DATASOURCE_URL` | `jdbc:sqlite:agent-runtime.db` |
| Postgres URL | `SPRING_DATASOURCE_URL` | `jdbc:postgresql://localhost:5432/conductor` |
| Postgres user | `SPRING_DATASOURCE_USERNAME` | `postgres` |
| Postgres password | `SPRING_DATASOURCE_PASSWORD` | `postgres` |
| Postgres pool size | `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` | `8` |

## Project Structure

```
├── cli/                  # Go CLI (agentspan server start/stop/logs)
├── server/               # Java runtime server (Spring Boot + Conductor)
│   └── src/
├── deployment/
│   ├── k8s/              # Kubernetes manifests
│   ├── helm/             # Helm chart
│   └── docker-compose/   # Compose stack (single node)
├── ui/                   # React workflow UI (served at localhost:8080)
├── sdk/
│   ├── python/           # Python SDK
│   │   ├── src/agentspan/agents/
│   │   ├── examples/     # 70+ progressive examples
│   │   └── validation/   # Multi-model validation framework
│   └── typescript/       # TypeScript SDK
│       ├── src/
│       └── examples/
└── docs/                 # Consolidated documentation
    ├── sdk-design/       # Multi-language SDK design specs
    ├── python-sdk/       # Python SDK reference docs
    └── server/           # Server documentation
```

## CLI Reference

```bash
agentspan server start     # Start the Agentspan server
agentspan server stop      # Stop the server
agentspan server logs      # View server logs
agentspan doctor           # Check system dependencies
```

## Community

We're building Agentspan in the open and would love your help.

- **[Discord](https://discord.gg/agentspan)** — Ask questions, share what you're building, get help
- **[GitHub Issues](https://github.com/agentspan/agentspan/issues)** — Bug reports and feature requests
- **[Contributing Guide](CONTRIBUTING.md)** — How to contribute code, docs, and examples

### Contributing

```bash
git clone https://github.com/agentspan/agentspan.git
cd agentspan/sdk/python
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

We welcome PRs of all sizes — from typo fixes to new examples to core features.

### Spread the Word

If Agentspan is useful to you, help others find it:

- [Star this repo](https://github.com/agentspan/agentspan) — it helps more than you think
- [Share on LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https://github.com/agentspan/agentspan) — tell your network
- [Share on X/Twitter](https://twitter.com/intent/tweet?text=Agentspan%20%E2%80%94%20AI%20agents%20that%20don%27t%20die%20when%20your%20process%20does.%20Durable%2C%20scalable%2C%20observable.&url=https://github.com/agentspan/agentspan) — spread the word
- [Share on Reddit](https://www.reddit.com/submit?url=https://github.com/agentspan/agentspan&title=Agentspan%20%E2%80%94%20AI%20agents%20that%20survive%20crashes%2C%20scale%20across%20machines%2C%20and%20pause%20for%20human%20approval%20for%20days) — post in r/MachineLearning or r/LocalLLaMA

## API Reference

See [API Reference](docs/python-sdk/api-reference.md) for the complete API reference and architecture guide.

## License

[MIT](LICENSE)
