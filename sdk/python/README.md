# Conductor Agents SDK for Python

The **agent-first** Python SDK for [Conductor](https://github.com/conductor-oss/conductor) — build durable, scalable, observable AI agents in 5 lines of code.

```python
from agentspan.agents import Agent, tool, run

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"

agent = Agent(name="weatherbot", model="openai/gpt-4o", tools=[get_weather])
result = run(agent, "What's the weather in NYC?")
```

Every other agent SDK runs agents in-memory. When the process dies, the agent dies. Conductor Agents gives you **durable, scalable, observable agent execution** — agents that survive crashes, tools that scale independently, and human-in-the-loop workflows that can pause for days.

## Why Conductor Agents?

| Capability | In-memory SDKs | Conductor Agents |
|---|---|---|
| Process crashes | Agent dies | **Agent continues** (workflow-backed) |
| Tool scaling | Single process | **Distributed workers, any language** |
| Human approval | Minutes at best | **Days/weeks** (native WaitTask) |
| Debugging | Log files | **Visual workflow UI** |
| Long-running | Process-bound | **Weeks** (workflow-bound) |
| Observability | Limited traces | **Prometheus + UI + execution history** |

## Quickstart

### Prerequisites

- Python 3.9+
- A running Conductor server with LLM support
- An LLM provider (e.g., `openai`) configured in Conductor

### Install

```bash
pip install agentspan-sdk
```

### Configure

Copy `.env.example` to `.env` and edit, or export env vars directly:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
export AGENT_LLM_MODEL=openai/gpt-4o-mini  # default; see examples/README.md for all providers
# For Orkes Cloud:
# export AGENTSPAN_AUTH_KEY=your_key
# export AGENTSPAN_AUTH_SECRET=your_secret
```

### Hello World

```python
from agentspan.agents import Agent, run

agent = Agent(name="hello", model="openai/gpt-4o")
result = run(agent, "Say hello and tell me a fun fact.")
print(result.output)
print(f"Workflow: {result.workflow_id}")  # View in Conductor UI
```

### Agent with Tools

```python
from agentspan.agents import Agent, tool, run

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

result = run(agent, "What's the weather in NYC? Also, what's 42 * 17?")
print(result.output)
```

### Structured Output

```python
from pydantic import BaseModel
from agentspan.agents import Agent, tool, run

class WeatherReport(BaseModel):
    city: str
    temperature: float
    condition: str
    recommendation: str

@tool
def get_weather(city: str) -> dict:
    """Get weather data for a city."""
    return {"city": city, "temp_f": 72, "condition": "Sunny", "humidity": 45}

agent = Agent(
    name="weather_reporter",
    model="openai/gpt-4o",
    tools=[get_weather],
    output_type=WeatherReport,
)

result = run(agent, "What's the weather in NYC?")
report: WeatherReport = result.output
print(f"{report.city}: {report.temperature}F, {report.condition}")
print(f"Recommendation: {report.recommendation}")
```

### Multi-Agent Handoffs

```python
from agentspan.agents import Agent, tool, run

@tool
def check_balance(account_id: str) -> dict:
    """Check account balance."""
    return {"account_id": account_id, "balance": 5432.10}

billing = Agent(
    name="billing",
    model="openai/gpt-4o",
    instructions="Handle billing: balances, payments, invoices.",
    tools=[check_balance],
)

technical = Agent(
    name="technical",
    model="openai/gpt-4o",
    instructions="Handle technical: orders, shipping, returns.",
)

support = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions="Route customer requests to billing or technical.",
    agents=[billing, technical],
    strategy="handoff",  # LLM chooses which sub-agent handles the request
)

result = run(support, "What's the balance on account ACC-123?")
```

### Sequential Pipeline

```python
from agentspan.agents import Agent, run

researcher = Agent(name="researcher", model="openai/gpt-4o",
                   instructions="Research the topic and provide key facts.")
writer = Agent(name="writer", model="openai/gpt-4o",
               instructions="Write an engaging article from the research.")
editor = Agent(name="editor", model="openai/gpt-4o",
               instructions="Polish the article for publication.")

# >> operator creates a sequential pipeline
pipeline = researcher >> writer >> editor
result = run(pipeline, "AI agents in software development")
print(result.output)
```

### Parallel Agents

```python
from agentspan.agents import Agent, run

market = Agent(name="market", model="openai/gpt-4o",
               instructions="Analyze market size, growth, key players.")
risk = Agent(name="risk", model="openai/gpt-4o",
             instructions="Analyze regulatory, technical, competitive risks.")

analysis = Agent(
    name="analysis",
    model="openai/gpt-4o",
    agents=[market, risk],
    strategy="parallel",  # Both run concurrently, results aggregated
)

result = run(analysis, "Launching an AI healthcare tool in the US")
```

### Human-in-the-Loop

```python
from agentspan.agents import Agent, tool, start

@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer funds. Requires human approval."""
    return {"status": "completed", "amount": amount}

agent = Agent(name="banker", model="openai/gpt-4o", tools=[transfer_funds])

handle = start(agent, "Transfer $5000 from checking to savings")
# Workflow pauses at transfer_funds...

# Hours or days later, from any process:
status = handle.get_status()
if status.is_waiting:
    handle.approve()   # Or: handle.reject("Amount too high")
```

### Guardrails

```python
from agentspan.agents import Agent, Guardrail, GuardrailResult, OnFail, guardrail, run

@guardrail
def word_limit(content: str) -> GuardrailResult:
    """Keep responses concise."""
    if len(content.split()) > 500:
        return GuardrailResult(passed=False, message="Too long. Be more concise.")
    return GuardrailResult(passed=True)

agent = Agent(
    name="concise_bot",
    model="openai/gpt-4o",
    guardrails=[Guardrail(word_limit, on_fail=OnFail.RETRY)],
)

result = run(agent, "Explain quantum computing.")
```

### Streaming

```python
from agentspan.agents import Agent, stream

agent = Agent(name="writer", model="openai/gpt-4o")
for event in stream(agent, "Write a haiku about Python"):
    match event.type:
        case "tool_call":       print(f"Calling {event.tool_name}...")
        case "thinking":        print(f"Thinking: {event.content}")
        case "guardrail_pass":  print(f"Guardrail passed: {event.guardrail_name}")
        case "guardrail_fail":  print(f"Guardrail failed: {event.guardrail_name}")
        case "done":            print(f"\n{event.output}")
```

### Server-Side Tools (No Workers Needed)

```python
from agentspan.agents import Agent, http_tool, mcp_tool, run

# HTTP endpoint as a tool — Conductor makes the call server-side
weather_api = http_tool(
    name="get_weather",
    description="Get weather for a city",
    url="https://api.weather.com/v1/current",
    method="GET",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
)

# MCP server tools — discovered at runtime
github = mcp_tool(server_url="http://localhost:8080/mcp")

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[weather_api, github])
```

## API Reference

See [AGENTS.md](AGENTS.md) for the complete API reference and architecture guide.

## Examples

| Example | Description |
|---|---|
| [`01_basic_agent.py`](examples/01_basic_agent.py) | 5-line hello world |
| [`02_tools.py`](examples/02_tools.py) | Multiple tools, approval |
| [`02a_simple_tools.py`](examples/02a_simple_tools.py) | Two tools, LLM picks the right one |
| [`02b_multi_step_tools.py`](examples/02b_multi_step_tools.py) | Chained lookups and calculations |
| [`03_structured_output.py`](examples/03_structured_output.py) | Pydantic output types |
| [`04_http_and_mcp_tools.py`](examples/04_http_and_mcp_tools.py) | Server-side HTTP and MCP tools |
| [`04_mcp_weather.py`](examples/04_mcp_weather.py) | MCP server tools (live weather) |
| [`05_handoffs.py`](examples/05_handoffs.py) | Agent delegation |
| [`06_sequential_pipeline.py`](examples/06_sequential_pipeline.py) | Agent >> Agent >> Agent |
| [`07_parallel_agents.py`](examples/07_parallel_agents.py) | Fan-out / fan-in |
| [`08_router_agent.py`](examples/08_router_agent.py) | LLM routing to specialists |
| [`09_human_in_the_loop.py`](examples/09_human_in_the_loop.py) | Approval workflows |
| [`09b_hitl_with_feedback.py`](examples/09b_hitl_with_feedback.py) | Custom feedback (respond API) |
| [`09c_hitl_streaming.py`](examples/09c_hitl_streaming.py) | Streaming + HITL approval |
| [`10_guardrails.py`](examples/10_guardrails.py) | Output validation + retry |
| [`11_streaming.py`](examples/11_streaming.py) | Real-time events |
| [`12_long_running.py`](examples/12_long_running.py) | Fire-and-forget with polling |
| [`13_hierarchical_agents.py`](examples/13_hierarchical_agents.py) | Nested agent teams |
| [`14_existing_workers.py`](examples/14_existing_workers.py) | Using existing Conductor workers as tools |
| [`15_agent_discussion.py`](examples/15_agent_discussion.py) | Round-robin debate between agents |
| [`16_random_strategy.py`](examples/16_random_strategy.py) | Random agent selection |
| [`17_swarm_orchestration.py`](examples/17_swarm_orchestration.py) | Swarm with handoff conditions |
| [`18_manual_selection.py`](examples/18_manual_selection.py) | Human picks which agent speaks |
| [`19_composable_termination.py`](examples/19_composable_termination.py) | Composable termination conditions |
| [`20_constrained_transitions.py`](examples/20_constrained_transitions.py) | Restricted agent transitions |
| [`21_regex_guardrails.py`](examples/21_regex_guardrails.py) | RegexGuardrail (block/allow patterns) |
| [`22_llm_guardrails.py`](examples/22_llm_guardrails.py) | LLMGuardrail (AI judge) |
| [`23_token_tracking.py`](examples/23_token_tracking.py) | Token usage and cost tracking |
| [`24_code_execution.py`](examples/24_code_execution.py) | Code execution sandboxes |
| [`25_semantic_memory.py`](examples/25_semantic_memory.py) | Long-term memory with retrieval |
| [`26_opentelemetry_tracing.py`](examples/26_opentelemetry_tracing.py) | OpenTelemetry spans for observability |
| [`27_user_proxy_agent.py`](examples/27_user_proxy_agent.py) | Human stand-in for interactive conversations |
| [`28_gpt_assistant_agent.py`](examples/28_gpt_assistant_agent.py) | OpenAI Assistants API wrapper |
| [`29_agent_introductions.py`](examples/29_agent_introductions.py) | Agents introduce themselves |
| [`30_multimodal_agent.py`](examples/30_multimodal_agent.py) | Image/video analysis with vision models |
| [`31_tool_guardrails.py`](examples/31_tool_guardrails.py) | Pre-execution validation on tool inputs |
| [`32_human_guardrail.py`](examples/32_human_guardrail.py) | Pause for human review on guardrail failure |
| [`33_external_workers.py`](examples/33_external_workers.py) | Reference workers in other services |
| [`34_prompt_templates.py`](examples/34_prompt_templates.py) | Reusable server-side prompt templates |
| [`35_standalone_guardrails.py`](examples/35_standalone_guardrails.py) | Guardrails as plain callables (no agent) |
| [`36_simple_agent_guardrails.py`](examples/36_simple_agent_guardrails.py) | Guardrails on agents without tools |
| [`37_fix_guardrail.py`](examples/37_fix_guardrail.py) | Auto-correct output with on_fail="fix" |
| [`38_tech_trends.py`](examples/38_tech_trends.py) | Tech trends research with tools |
| [`39_local_code_execution.py`](examples/39_local_code_execution.py) | Local code execution sandbox |
| [`40_media_generation_agent.py`](examples/40_media_generation_agent.py) | Image/audio/video generation tools |
| [`41_sequential_pipeline_tools.py`](examples/41_sequential_pipeline_tools.py) | Sequential pipeline with per-stage tools |
| [`42_security_testing.py`](examples/42_security_testing.py) | Red-team security testing pipeline |
| [`43_data_security_pipeline.py`](examples/43_data_security_pipeline.py) | Data fetch, redact, and respond pipeline |
| [`44_safety_guardrails.py`](examples/44_safety_guardrails.py) | PII detection and sanitization pipeline |

### Google ADK Compatibility

We provide a full compatibility layer for [Google ADK](https://github.com/google/adk-python) — use the same `google.adk.agents` API backed by Conductor's durable execution. See [`examples/adk/`](examples/adk/) for 28 examples covering Agent, SequentialAgent, ParallelAgent, LoopAgent, sub_agents, AgentTool, callbacks, and more.

```python
from google.adk.agents import Agent, SequentialAgent

researcher = Agent(name="researcher", model="gemini-2.0-flash",
                   instruction="Research the topic.", tools=[search])
writer = Agent(name="writer", model="gemini-2.0-flash",
               instruction="Write an article from the research.")

pipeline = SequentialAgent(name="pipeline", sub_agents=[researcher, writer])
```

See [ADK Samples Status](examples/adk/ADK_SAMPLES_STATUS.md) for full Google ADK coverage details.

## License

Apache 2.0
