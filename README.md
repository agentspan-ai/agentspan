# AgentSpan

Build **durable, scalable, observable AI agents** backed by [Conductor](https://github.com/conductor-oss/conductor) workflows.

```python
from conductor.agents import Agent, tool, run

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"

agent = Agent(name="weatherbot", model="openai/gpt-4o", tools=[get_weather])
result = run(agent, "What's the weather in NYC?")
```

Every other agent SDK runs agents in-memory. When the process dies, the agent dies. AgentSpan compiles agents into **durable Conductor workflows** — agents that survive crashes, tools that scale as distributed workers, and human-in-the-loop approvals that can pause for days.

## Why AgentSpan?

| Capability | In-memory SDKs | AgentSpan |
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
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A running Conductor server with LLM support
- An LLM provider (e.g., `openai`) configured in Conductor

### Install

```bash
# Create and activate a virtual environment
uv venv
source .venv/bin/activate

# Install from the local python/ directory
uv pip install -e "./python[dev]"
```

### Configure

```bash
export CONDUCTOR_SERVER_URL=http://localhost:7001/api
# For Orkes Cloud:
# export CONDUCTOR_AUTH_KEY=your_key
# export CONDUCTOR_AUTH_SECRET=your_secret
```

### Hello World

```python
from conductor.agents import Agent, run

agent = Agent(name="hello", model="openai/gpt-4o")
result = run(agent, "Say hello and tell me a fun fact.")
print(result.output)
print(f"Workflow: {result.workflow_id}")  # View in Conductor UI
```

### Agent with Tools

```python
from conductor.agents import Agent, tool, run

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
from conductor.agents import Agent, tool, run

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
```

### Multi-Agent Handoffs

```python
from conductor.agents import Agent, tool, run

@tool
def check_balance(account_id: str) -> dict:
    """Check account balance."""
    return {"account_id": account_id, "balance": 5432.10}

billing = Agent(
    name="billing", model="openai/gpt-4o",
    instructions="Handle billing: balances, payments, invoices.",
    tools=[check_balance],
)
technical = Agent(
    name="technical", model="openai/gpt-4o",
    instructions="Handle technical: orders, shipping, returns.",
)
support = Agent(
    name="support", model="openai/gpt-4o",
    instructions="Route customer requests to billing or technical.",
    agents=[billing, technical],
    strategy="handoff",
)

result = run(support, "What's the balance on account ACC-123?")
```

### Sequential Pipeline

```python
from conductor.agents import Agent, run

researcher = Agent(name="researcher", model="openai/gpt-4o",
                   instructions="Research the topic and provide key facts.")
writer = Agent(name="writer", model="openai/gpt-4o",
               instructions="Write an engaging article from the research.")
editor = Agent(name="editor", model="openai/gpt-4o",
               instructions="Polish the article for publication.")

pipeline = researcher >> writer >> editor
result = run(pipeline, "AI agents in software development")
```

### Parallel Agents

```python
from conductor.agents import Agent, run

market = Agent(name="market", model="openai/gpt-4o",
               instructions="Analyze market size, growth, key players.")
risk = Agent(name="risk", model="openai/gpt-4o",
             instructions="Analyze regulatory, technical, competitive risks.")

analysis = Agent(
    name="analysis", model="openai/gpt-4o",
    agents=[market, risk],
    strategy="parallel",
)

result = run(analysis, "Launching an AI healthcare tool in the US")
```

### Human-in-the-Loop

```python
from conductor.agents import Agent, tool, start

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
from conductor.agents import Agent, Guardrail, GuardrailResult, RegexGuardrail, run

# Function-based guardrail
def word_limit(content: str) -> GuardrailResult:
    if len(content.split()) > 500:
        return GuardrailResult(passed=False, message="Too long. Be more concise.")
    return GuardrailResult(passed=True)

# Regex-based guardrail (block PII)
no_ssn = RegexGuardrail(
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
    name="no_ssn",
    message="Do not include SSNs.",
)

agent = Agent(
    name="safe_bot", model="openai/gpt-4o",
    guardrails=[
        Guardrail(word_limit, position="output", on_fail="retry"),
        no_ssn,
    ],
)
```

### Streaming

```python
from conductor.agents import Agent, stream

agent = Agent(name="writer", model="openai/gpt-4o")
for event in stream(agent, "Write a haiku about Python"):
    match event.type:
        case "tool_call":   print(f"Calling {event.tool_name}...")
        case "thinking":    print(f"Thinking: {event.content}")
        case "done":        print(f"\n{event.output}")
```

### Server-Side Tools (No Workers Needed)

```python
from conductor.agents import Agent, http_tool, mcp_tool, run

# HTTP endpoint as a tool
weather_api = http_tool(
    name="get_weather",
    description="Get weather for a city",
    url="https://api.weather.com/v1/current",
    method="GET",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
)

# MCP server tools
github = mcp_tool(server_url="http://localhost:8080/mcp")

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[weather_api, github])
```

### Code Execution

```python
from conductor.agents import Agent
from conductor.agents.code_executor import DockerCodeExecutor

executor = DockerCodeExecutor(image="python:3.12-slim", timeout=30)
agent = Agent(
    name="coder", model="openai/gpt-4o",
    tools=[executor.as_tool()],
    instructions="Write and execute Python code to solve problems.",
)
```

### Shared State (Tool Context)

```python
from conductor.agents import Agent, tool, ToolContext, run

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

result = run(agent, "Add apples, bananas, and cherries, then show the list.")
```

## Multi-Agent Strategies

| Strategy | Description | Conductor Mapping |
|---|---|---|
| `handoff` (default) | LLM chooses which sub-agent handles the request | SwitchTask + InlineSubWorkflow |
| `sequential` | Sub-agents run in order, output feeds forward (`>>` operator) | Chain of SubWorkflowTask |
| `parallel` | All sub-agents run concurrently, results aggregated | ForkTask + JoinTask |
| `router` | Router agent or function selects the sub-agent | LlmChatComplete + SwitchTask |
| `round_robin` | Agents take turns in a fixed rotation | DoWhile with turn tracking |
| `swarm` | Condition-based handoffs between agents | DoWhile + HandoffConditions |
| `random` | Random sub-agent selection each turn | DoWhile with random selection |

## Supported LLM Providers

Any provider configured as an AI integration in Conductor:

| Provider | Model Format |
|---|---|
| OpenAI | `openai/gpt-4o` |
| Anthropic | `anthropic/claude-sonnet-4-20250514` |
| Azure OpenAI | `azure_openai/gpt-4o` |
| Google Gemini | `google_gemini/gemini-pro` |
| Google Vertex AI | `google_vertex_ai/gemini-pro` |
| AWS Bedrock | `aws_bedrock/anthropic.claude-v2` |
| Cohere | `cohere/command-r-plus` |
| Mistral | `mistral/mistral-large` |
| Groq | `groq/llama-3-70b` |
| Perplexity | `perplexity/sonar-medium` |
| Hugging Face | `hugging_face/meta-llama/Llama-3-70b` |
| DeepSeek | `deepseek/deepseek-chat` |

## Public API

All exports from `conductor.agents`:

```python
# Core
Agent, AgentDef, AgentRuntime, AgentConfig, Strategy, PromptTemplate

# Extended agent types
UserProxyAgent, GPTAssistantAgent

# Tools
tool, ToolDef, ToolContext, agent_tool, http_tool, mcp_tool
image_tool, audio_tool, video_tool, pdf_tool
clear_discovery_cache

# Execution
run, run_async, start, stream, plan, shutdown

# Results
AgentResult, AgentHandle, AgentStatus, AgentStream, AgentEvent, EventType, TokenUsage

# Guardrails
guardrail, Guardrail, GuardrailDef, GuardrailResult, OnFail, Position
RegexGuardrail, LLMGuardrail

# Termination conditions
TerminationCondition, TerminationResult
TextMentionTermination, StopMessageTermination, MaxMessageTermination, TokenUsageTermination

# Memory
ConversationMemory, SemanticMemory, MemoryStore, MemoryEntry

# Code execution
CodeExecutionConfig, CodeExecutor, LocalCodeExecutor, DockerCodeExecutor
JupyterCodeExecutor, ServerlessCodeExecutor, ExecutionResult

# Handoff conditions (swarm strategy)
HandoffCondition, OnToolResult, OnTextMention, OnCondition

# Tracing
is_tracing_enabled
```

## Examples

| Example | Description |
|---|---|
| [`01_basic_agent.py`](python/examples/01_basic_agent.py) | 5-line hello world |
| [`02_tools.py`](python/examples/02_tools.py) | Multiple tools with approval |
| [`02a_simple_tools.py`](python/examples/02a_simple_tools.py) | Two tools, LLM picks the right one |
| [`02b_multi_step_tools.py`](python/examples/02b_multi_step_tools.py) | Chained lookups and calculations |
| [`03_structured_output.py`](python/examples/03_structured_output.py) | Pydantic output types |
| [`04_mcp_weather.py`](python/examples/04_mcp_weather.py) | MCP server tools (live weather) |
| [`04_http_and_mcp_tools.py`](python/examples/04_http_and_mcp_tools.py) | HTTP and MCP server-side tools |
| [`05_handoffs.py`](python/examples/05_handoffs.py) | Agent delegation |
| [`06_sequential_pipeline.py`](python/examples/06_sequential_pipeline.py) | Agent >> Agent >> Agent |
| [`07_parallel_agents.py`](python/examples/07_parallel_agents.py) | Fan-out / fan-in |
| [`08_router_agent.py`](python/examples/08_router_agent.py) | LLM routing to specialists |
| [`09_human_in_the_loop.py`](python/examples/09_human_in_the_loop.py) | Approval workflows |
| [`09b_hitl_with_feedback.py`](python/examples/09b_hitl_with_feedback.py) | Custom feedback (respond API) |
| [`09c_hitl_streaming.py`](python/examples/09c_hitl_streaming.py) | Streaming + HITL approval |
| [`10_guardrails.py`](python/examples/10_guardrails.py) | Output validation + retry |
| [`11_streaming.py`](python/examples/11_streaming.py) | Real-time events |
| [`12_long_running.py`](python/examples/12_long_running.py) | Fire-and-forget with polling |
| [`13_hierarchical_agents.py`](python/examples/13_hierarchical_agents.py) | Nested agent teams |
| [`14_existing_workers.py`](python/examples/14_existing_workers.py) | Using existing Conductor workers |
| [`15_agent_discussion.py`](python/examples/15_agent_discussion.py) | Round-robin debate |
| [`16_random_strategy.py`](python/examples/16_random_strategy.py) | Random agent selection |
| [`17_swarm_orchestration.py`](python/examples/17_swarm_orchestration.py) | Condition-based handoffs |
| [`18_manual_selection.py`](python/examples/18_manual_selection.py) | Manual agent selection |
| [`19_composable_termination.py`](python/examples/19_composable_termination.py) | Composable stop conditions |
| [`20_constrained_transitions.py`](python/examples/20_constrained_transitions.py) | Allowed agent transitions |
| [`21_regex_guardrails.py`](python/examples/21_regex_guardrails.py) | Regex-based guardrails |
| [`22_llm_guardrails.py`](python/examples/22_llm_guardrails.py) | LLM-powered guardrails |
| [`23_token_tracking.py`](python/examples/23_token_tracking.py) | Token usage tracking |
| [`24_code_execution.py`](python/examples/24_code_execution.py) | Sandboxed code execution |
| [`25_semantic_memory.py`](python/examples/25_semantic_memory.py) | Long-term memory with similarity search |
| [`26_opentelemetry_tracing.py`](python/examples/26_opentelemetry_tracing.py) | OpenTelemetry spans |
| [`27_user_proxy_agent.py`](python/examples/27_user_proxy_agent.py) | Human-in-the-loop proxy agent |
| [`28_gpt_assistant_agent.py`](python/examples/28_gpt_assistant_agent.py) | OpenAI Assistants integration |
| [`29_agent_introductions.py`](python/examples/29_agent_introductions.py) | Agent self-introductions |
| [`30_multimodal_agent.py`](python/examples/30_multimodal_agent.py) | Images, video, audio input |
| [`31_tool_guardrails.py`](python/examples/31_tool_guardrails.py) | Per-tool guardrails |
| [`32_human_guardrail.py`](python/examples/32_human_guardrail.py) | Human review guardrail |
| [`33_external_workers.py`](python/examples/33_external_workers.py) | Reference workers in other services |
| [`33_single_turn_tool.py`](python/examples/33_single_turn_tool.py) | Single-turn tool call |
| [`34_prompt_templates.py`](python/examples/34_prompt_templates.py) | Reusable, versioned prompt templates |
| [`35_standalone_guardrails.py`](python/examples/35_standalone_guardrails.py) | Guardrails as plain callables |
| [`36_simple_agent_guardrails.py`](python/examples/36_simple_agent_guardrails.py) | Output validation without tools |
| [`37_fix_guardrail.py`](python/examples/37_fix_guardrail.py) | Auto-correct output instead of retry |
| [`38_tech_trends.py`](python/examples/38_tech_trends.py) | Tech trends analysis |
| [`39_local_code_execution.py`](python/examples/39_local_code_execution.py) | Local code execution |
| [`40_media_generation_agent.py`](python/examples/40_media_generation_agent.py) | Media generation |
| [`41_sequential_pipeline_tools.py`](python/examples/41_sequential_pipeline_tools.py) | Sequential pipeline with stage-level tools |
| [`42_security_testing.py`](python/examples/42_security_testing.py) | Red-team AI safety evaluation |
| [`43_data_security_pipeline.py`](python/examples/43_data_security_pipeline.py) | Controlled data flow with redaction |
| [`44_safety_guardrails.py`](python/examples/44_safety_guardrails.py) | PII detection and sanitization |
| [`45_agent_tool.py`](python/examples/45_agent_tool.py) | Wrap an agent as a callable tool |
| [`46_transfer_control.py`](python/examples/46_transfer_control.py) | Restrict agent handoff targets |
| [`47_callbacks.py`](python/examples/47_callbacks.py) | Lifecycle hooks (before/after LLM) |
| [`48_planner.py`](python/examples/48_planner.py) | Plan-then-execute agent |
| [`49_include_contents.py`](python/examples/49_include_contents.py) | Control context passed to sub-agents |
| [`50_thinking_config.py`](python/examples/50_thinking_config.py) | Extended reasoning for complex tasks |
| [`51_shared_state.py`](python/examples/51_shared_state.py) | Tools sharing state via ToolContext |
| [`52_nested_strategies.py`](python/examples/52_nested_strategies.py) | Parallel agents inside sequential pipeline |

## Project Structure

```
python/
├── src/conductor/agents/
│   ├── __init__.py                 # Public API exports
│   ├── agent.py                    # Agent, AgentDef, Strategy
│   ├── tool.py                     # @tool, ToolDef, ToolContext, http_tool, mcp_tool
│   ├── run.py                      # run, start, stream, run_async, plan, shutdown
│   ├── result.py                   # AgentResult, AgentHandle, AgentEvent, EventType
│   ├── config_serializer.py        # Serializes Agent tree → JSON for server
│   ├── guardrail.py                # Guardrail, GuardrailResult, RegexGuardrail, LLMGuardrail
│   ├── memory.py                   # ConversationMemory
│   ├── semantic_memory.py          # SemanticMemory, MemoryStore, MemoryEntry
│   ├── termination.py              # TerminationCondition and subclasses
│   ├── handoff.py                  # HandoffCondition, OnToolResult, OnTextMention, OnCondition
│   ├── code_executor.py            # CodeExecutor, Docker/Local/Jupyter/Serverless
│   ├── code_execution_config.py    # CodeExecutionConfig
│   ├── ext.py                      # UserProxyAgent, GPTAssistantAgent
│   ├── tracing.py                  # OpenTelemetry integration
│   ├── runtime/                    # Workflow execution and tool dispatch
│   │   ├── runtime.py              # AgentRuntime (run/start/stream)
│   │   ├── config.py               # AgentConfig (env vars)
│   │   ├── tool_registry.py        # ToolRegistry (worker registration)
│   │   ├── _dispatch.py            # Tool worker dispatch
│   │   ├── mcp_discovery.py        # MCP tool discovery
│   │   └── worker_manager.py       # Worker lifecycle management
│   └── _internal/                  # Shared utilities
│       ├── model_parser.py
│       ├── provider_registry.py
│       └── schema_utils.py
├── examples/                       # 52 progressive examples
├── tests/
│   ├── unit/                       # Unit tests (no server required)
│   └── integration/                # Integration tests (require Conductor server)
├── pyproject.toml
├── DESIGN.md                       # Internal architecture documentation
└── REQUIREMENTS.md                 # Detailed requirements specification
```

## Development

```bash
# Create virtual environment and install with dev dependencies
uv venv
source .venv/bin/activate
uv pip install -e "./python[dev]"

# Run unit tests
cd python && python3 -m pytest tests/unit/ -v

# Lint
ruff check python/src/

# Type check
mypy python/src/conductor/agents/ --ignore-missing-imports
```

## License

Apache 2.0
