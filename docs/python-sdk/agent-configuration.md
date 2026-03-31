# Agent Configuration Reference

Complete reference for configuring agents, tools, guardrails, memory, termination, and runtime.

---

## Agent

The `Agent` class is the central building block. It can represent a single LLM agent, a multi-agent orchestration, or an external workflow reference.

```python
from agentspan.agents import Agent

agent = Agent(
    name="my_agent",
    model="openai/gpt-4o",
    instructions="You are a helpful assistant.",
    tools=[my_tool],
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | **required** | Unique agent name. Used as the Conductor workflow name. Must start with a letter or underscore; may contain letters, digits, underscores, hyphens. |
| `model` | `str` | `""` | LLM model in `"provider/model"` format (e.g. `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4-20250514"`). Empty string means the agent is external (references a workflow deployed elsewhere). |
| `instructions` | `str \| Callable[..., str] \| PromptTemplate` | `""` | System prompt. Can be a static string, a callable returning a string, or a `PromptTemplate` referencing a server-side template. |
| `tools` | `list` | `None` | List of tools: `@tool`-decorated functions, `ToolDef` instances from `http_tool()`, `mcp_tool()`, `image_tool()`, `audio_tool()`, `video_tool()`, or `@worker_task`-decorated functions. |
| `agents` | `list[Agent]` | `None` | Sub-agents for multi-agent orchestration. Accepts `Agent` instances and `@agent`-decorated functions. |
| `strategy` | `str \| Strategy` | `"handoff"` | Multi-agent strategy (only relevant when `agents` is set). See [Strategies](#strategies). |
| `router` | `Agent \| Callable` | `None` | Router agent or callable for `strategy="router"`. **Required** when strategy is `"router"`. |
| `output_type` | `type` | `None` | Pydantic `BaseModel` or dataclass for structured JSON output. The schema is injected into the system prompt and `jsonOutput=True` is set on the LLM task. |
| `guardrails` | `list[Guardrail]` | `None` | Input/output validation guardrails. See [Guardrails](#guardrails). |
| `memory` | `ConversationMemory \| SemanticMemory` | `None` | Memory for session management. `ConversationMemory` for chat history; `SemanticMemory` for similarity-based retrieval. |
| `dependencies` | `dict[str, Any]` | `None` | Dependencies injected into tool `ToolContext` at runtime (e.g. DB connections, API clients). |
| `max_turns` | `int` | `25` | Maximum DoWhile loop iterations. Must be >= 1. |
| `max_tokens` | `int` | `None` | Maximum tokens for LLM generation. |
| `timeout_seconds` | `int` | `0` | Execution-level timeout in seconds. `0` means no timeout. |
| `temperature` | `float` | `None` | LLM sampling temperature. |
| `stop_when` | `Callable[..., bool]` | `None` | Callable `(context) -> bool` evaluated each loop iteration. Returns `True` to stop the agent. Context dict has `result`, `messages`, `iteration`. |
| `termination` | `TerminationCondition` | `None` | Composable termination condition. Can be combined with `&` (AND) and `\|` (OR). See [Termination Conditions](#termination-conditions). |
| `handoffs` | `list[HandoffCondition]` | `None` | Handoff rules for `strategy="swarm"`. See [Handoff Conditions](#handoff-conditions). |
| `allowed_transitions` | `dict[str, list[str]]` | `None` | Constrains which agents can follow which in round-robin/random strategies. Map of `agent_name -> [allowed_next_agents]`. |
| `introduction` | `str` | `None` | Text this agent uses to introduce itself in group conversations (round-robin, random, swarm, manual). |
| `metadata` | `dict[str, Any]` | `None` | Arbitrary metadata attached to the agent and its compiled workflow. |
| `local_code_execution` | `bool` | `False` | When `True`, attaches an `execute_code` tool backed by `LocalCodeExecutor`. |
| `allowed_languages` | `list[str]` | `None` | Languages the LLM may use when `local_code_execution` is enabled. Defaults to `["python"]`. Supported: `python`, `bash`, `sh`, `node`, `javascript`, `ruby`. |
| `allowed_commands` | `list[str]` | `None` | Shell commands code execution may invoke (e.g. `["pip", "ls"]`). Empty list means no restrictions. |
| `code_execution` | `CodeExecutionConfig` | `None` | Full control over code execution. Mutually exclusive with `local_code_execution`. |

### Agent Composition

The `>>` operator creates sequential pipelines:

```python
pipeline = researcher >> writer >> editor  # strategy="sequential"
```

### @agent Decorator

```python
@agent
def my_agent():
    """System prompt from docstring."""

@agent(model="openai/gpt-4o", tools=[search])
def my_agent():
    """System prompt."""
```

All `Agent.__init__` parameters (except `name`) are accepted as decorator arguments. The function name becomes the agent name.

---

## Strategies

Used when an agent has sub-agents (`agents` parameter).

| Strategy | Description |
|----------|-------------|
| `"handoff"` | Parent LLM selects which sub-agent to delegate to. |
| `"sequential"` | Sub-agents run in order. Output of agent N becomes input of agent N+1. |
| `"parallel"` | All sub-agents run concurrently. Results aggregated. |
| `"router"` | A router agent or callable selects which sub-agent runs. Requires `router` parameter. |
| `"round_robin"` | Sub-agents take turns in fixed rotation inside a DoWhile loop. |
| `"random"` | Like round-robin but with random agent selection each turn. |
| `"swarm"` | Agents run with post-turn handoff conditions (`handoffs` parameter). |
| `"manual"` | Human selects which agent speaks next each iteration via HumanTask. |

---

## Tools

### @tool Decorator

```python
from agentspan.agents import tool

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Sunny in {city}"

@tool(approval_required=True, timeout_seconds=60)
def send_email(to: str, body: str) -> str:
    """Send an email. Requires human approval."""
    ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | function name | Override tool name. |
| `external` | `bool` | `False` | If `True`, no local worker is started. The tool runs as a remote Conductor worker. |
| `approval_required` | `bool` | `False` | If `True`, a HumanTask gate is inserted before tool execution. |
| `timeout_seconds` | `int` | `None` | Max execution time in seconds. |
| `guardrails` | `list` | `None` | Tool-level guardrails (input/output). |

### ToolContext

Tools can request a `ToolContext` by adding a `context` parameter:

```python
@tool
def my_tool(query: str, context: ToolContext) -> str:
    print(context.session_id, context.execution_id, context.agent_name)
    db = context.dependencies["db"]
    ...
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Session ID for current execution. |
| `execution_id` | `str` | Execution ID. |
| `agent_name` | `str` | Name of the agent executing this tool. |
| `metadata` | `dict` | Agent metadata. |
| `dependencies` | `dict` | User-provided dependencies from `Agent(dependencies={...})`. |

### http_tool

```python
from agentspan.agents import http_tool

api = http_tool(
    name="search_api",
    description="Search the web.",
    url="https://api.example.com/search",
    method="POST",
    headers={"Authorization": "Bearer ..."},
    input_schema={...},
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | **required** | Tool name. |
| `description` | `str` | **required** | Description for the LLM. |
| `url` | `str` | **required** | HTTP endpoint URL. |
| `method` | `str` | `"GET"` | HTTP method. |
| `headers` | `dict` | `None` | HTTP headers. |
| `input_schema` | `dict` | `None` | JSON Schema for parameters. |

No worker process needed. Conductor executes the HTTP call directly.

### mcp_tool

```python
from agentspan.agents import mcp_tool

tools = mcp_tool(
    server_url="http://localhost:3001/mcp",
    headers={"Authorization": "Bearer ..."},
    tool_names=["search", "fetch"],  # optional whitelist
    max_tools=64,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server_url` | `str` | **required** | URL of the MCP server. |
| `name` | `str` | `"mcp_tools"` | Override name. |
| `description` | `str` | auto | Override description. |
| `headers` | `dict` | `None` | HTTP headers for MCP auth. |
| `tool_names` | `list[str]` | `None` | Whitelist of tool names. |
| `max_tools` | `int` | `64` | If discovered tools exceed this, a runtime LLM filter step selects relevant tools per-request. |

Tools are discovered at compile time via Conductor's `LIST_MCP_TOOLS` system task and expanded into individual tool definitions.

### image_tool

```python
from agentspan.agents import image_tool

gen_image = image_tool(
    name="generate_image",
    description="Generate an image from a text description.",
    llm_provider="openai",
    model="dall-e-3",
    n=1,                    # static default
    outputFormat="png",     # static default
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | **required** | Tool name. |
| `description` | `str` | **required** | Description for the LLM. |
| `llm_provider` | `str` | **required** | AI provider integration name (e.g. `"openai"`). |
| `model` | `str` | **required** | Model name (e.g. `"dall-e-3"`, `"gpt-image-1"`). |
| `input_schema` | `dict` | see below | JSON Schema for LLM-provided parameters. |
| `**defaults` | `Any` | — | Static parameters passed to the generation task. |

Default input schema (LLM-visible parameters):

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `prompt` | `string` | **required** | Text description of the image. |
| `style` | `string` | — | Image style: `"vivid"` or `"natural"`. |
| `width` | `integer` | `1024` | Image width in pixels. |
| `height` | `integer` | `1024` | Image height in pixels. |
| `size` | `string` | — | Alternative to width/height (e.g. `"1024x1024"`). |
| `n` | `integer` | `1` | Number of images to generate. |
| `outputFormat` | `string` | `"png"` | Output format: `"png"`, `"jpg"`, or `"webp"`. |
| `weight` | `number` | — | Image weight parameter. |

### audio_tool

```python
from agentspan.agents import audio_tool

tts = audio_tool(
    name="text_to_speech",
    description="Convert text to spoken audio.",
    llm_provider="openai",
    model="tts-1",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | **required** | Tool name. |
| `description` | `str` | **required** | Description for the LLM. |
| `llm_provider` | `str` | **required** | AI provider integration name. |
| `model` | `str` | **required** | Model name (e.g. `"tts-1"`). |
| `input_schema` | `dict` | see below | JSON Schema for LLM-provided parameters. |
| `**defaults` | `Any` | — | Static parameters. |

Default input schema:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `text` | `string` | **required** | Text to convert to speech. |
| `voice` | `string` | `"alloy"` | Voice: `"alloy"`, `"echo"`, `"fable"`, `"onyx"`, `"nova"`, `"shimmer"`. |
| `speed` | `number` | `1.0` | Speech speed multiplier (0.25 to 4.0). |
| `responseFormat` | `string` | `"mp3"` | Audio format: `"mp3"`, `"wav"`, `"opus"`, `"aac"`, `"flac"`. |
| `n` | `integer` | `1` | Number of audio outputs. |

### video_tool

```python
from agentspan.agents import video_tool

gen_video = video_tool(
    name="generate_video",
    description="Generate a short video clip.",
    llm_provider="openai",
    model="sora-2",
    size="1280x720",  # static default
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | **required** | Tool name. |
| `description` | `str` | **required** | Description for the LLM. |
| `llm_provider` | `str` | **required** | AI provider integration name. |
| `model` | `str` | **required** | Model name (e.g. `"sora-2"`). |
| `input_schema` | `dict` | see below | JSON Schema for LLM-provided parameters. |
| `**defaults` | `Any` | — | Static parameters. |

Default input schema:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `prompt` | `string` | **required** | Text description of the video scene. |
| `inputImage` | `string` | — | Base64-encoded or URL image for image-to-video. |
| `duration` | `integer` | `5` | Duration in seconds. |
| `width` | `integer` | `1280` | Video width in pixels. |
| `height` | `integer` | `720` | Video height in pixels. |
| `fps` | `integer` | `24` | Frames per second. |
| `outputFormat` | `string` | `"mp4"` | Video format. |
| `style` | `string` | — | Video style (e.g. `"cinematic"`, `"natural"`). |
| `motion` | `string` | — | Movement intensity (e.g. `"slow"`, `"normal"`, `"extreme"`). |
| `seed` | `integer` | — | Seed for reproducibility. |
| `guidanceScale` | `number` | — | Prompt adherence strength (1.0 to 20.0). |
| `aspectRatio` | `string` | — | Aspect ratio (e.g. `"16:9"`, `"1:1"`). |
| `negativePrompt` | `string` | — | What to exclude from the video. |
| `personGeneration` | `string` | — | Controls for human figure generation. |
| `resolution` | `string` | — | Quality level (e.g. `"720p"`, `"1080p"`). |
| `generateAudio` | `boolean` | — | Whether to generate audio with the video. |
| `size` | `string` | — | Size specification (e.g. `"1280x720"`). |
| `n` | `integer` | `1` | Number of videos to generate. |
| `maxDurationSeconds` | `integer` | — | Maximum duration ceiling. |
| `maxCostDollars` | `number` | — | Maximum cost limit in dollars. |

### Media Tool Defaults Pipeline

For all media tools, static parameters (`llmProvider`, `model`, and any `**defaults`) are baked into the compiled workflow. At runtime, the LLM provides dynamic parameters from the `input_schema`. Defaults and LLM parameters are merged — LLM values override defaults.

---

## Guardrails

Guardrails validate agent input/output and take corrective action on failure.

### Guardrail

```python
from agentspan.agents import Guardrail, guardrail, GuardrailResult

@guardrail
def no_profanity(content: str) -> GuardrailResult:
    """Block profane content."""
    if has_profanity(content):
        return GuardrailResult(passed=False, message="Content contains profanity.")
    return GuardrailResult(passed=True)

agent = Agent(
    ...,
    guardrails=[
        Guardrail(no_profanity, position="output", on_fail="retry", max_retries=3),
    ],
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `func` | `Callable` | `None` | Callable that validates content and returns `GuardrailResult`. If `None` and `name` is provided, treated as external (remote worker). |
| `position` | `str` | `"output"` | `"input"` — validate before LLM call. `"output"` — validate after LLM response. |
| `on_fail` | `str` | `"retry"` | `"retry"` — re-prompt the LLM with feedback. `"raise"` — terminate the execution. `"fix"` — use `fixed_output` from `GuardrailResult`. `"human"` — route to human for approval/edit/rejection. |
| `name` | `str` | function name | Guardrail name. |
| `max_retries` | `int` | `3` | Maximum retry attempts for `on_fail="retry"`. After exhausting retries, escalates to `"raise"`. |

### GuardrailResult

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `passed` | `bool` | **required** | `True` if content passes validation. |
| `message` | `str` | `""` | Feedback message sent to LLM on retry. |
| `fixed_output` | `str` | `None` | Corrected output for `on_fail="fix"`. |

### RegexGuardrail

Server-side regex validation (no worker needed).

```python
from agentspan.agents import RegexGuardrail

no_emails = RegexGuardrail(
    patterns=[r"[\w.-]+@[\w.-]+\.\w+"],
    mode="block",
    position="output",
    on_fail="retry",
    message="Do not include email addresses.",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `patterns` | `str \| list[str]` | **required** | Regex patterns. |
| `mode` | `str` | `"block"` | `"block"` — fail if any pattern matches. `"allow"` — fail if NO pattern matches. |
| `position` | `str` | `"output"` | `"input"` or `"output"`. |
| `on_fail` | `str` | `"retry"` | `"retry"` or `"raise"`. |
| `name` | `str` | `None` | Guardrail name. |
| `message` | `str` | `None` | Custom failure message. |
| `max_retries` | `int` | `3` | Maximum retries. |

### LLMGuardrail

Uses a second LLM to evaluate content against a policy.

```python
from agentspan.agents import LLMGuardrail

safe_content = LLMGuardrail(
    model="openai/gpt-4o-mini",
    policy="Content must be appropriate for all ages. No violence or adult themes.",
    position="output",
    on_fail="retry",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | **required** | LLM model in `"provider/model"` format. |
| `policy` | `str` | **required** | What the guardrail should check for. |
| `position` | `str` | `"output"` | `"input"` or `"output"`. |
| `on_fail` | `str` | `"retry"` | `"retry"` or `"raise"`. |
| `name` | `str` | `None` | Guardrail name. |
| `max_retries` | `int` | `3` | Maximum retries. |
| `max_tokens` | `int` | `None` | Max tokens for the evaluator LLM. |

---

## Memory

### ConversationMemory

Chat history that accumulates messages across interactions.

```python
from agentspan.agents import ConversationMemory

memory = ConversationMemory(max_messages=100)
agent = Agent(..., memory=memory)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `messages` | `list[dict]` | `[]` | Accumulated conversation messages. |
| `max_messages` | `int` | `None` | Maximum messages to retain (oldest trimmed). |

Methods: `add_user_message()`, `add_assistant_message()`, `add_system_message()`, `add_tool_call()`, `add_tool_result()`, `to_chat_messages()`, `clear()`.

### SemanticMemory

Similarity-based memory retrieval with short-term and long-term storage.

```python
from agentspan.agents.semantic_memory import SemanticMemory

memory = SemanticMemory(max_results=5)
memory.add("User prefers Python over JavaScript")
results = memory.search("What language does the user like?")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `store` | `MemoryStore` | `InMemoryStore()` | Storage backend. |
| `max_results` | `int` | `5` | Maximum memories per query. |
| `session_id` | `str` | `None` | Session scope for memories. |

Methods: `add()`, `search()`, `get_context()`, `delete()`, `clear()`, `list_all()`.

---

## Termination Conditions

Composable conditions that control when the agent loop stops.

```python
from agentspan.agents import (
    TextMentionTermination, StopMessageTermination,
    MaxMessageTermination, TokenUsageTermination,
)

# Single condition
stop = TextMentionTermination("DONE")

# Composed: stop on DONE OR after 50 messages
stop = TextMentionTermination("DONE") | MaxMessageTermination(50)

# Composed: stop on FINAL AND at least 10 messages
stop = TextMentionTermination("FINAL") & MaxMessageTermination(10)

agent = Agent(..., termination=stop)
```

| Condition | Parameters | Description |
|-----------|-----------|-------------|
| `TextMentionTermination` | `text: str`, `case_sensitive: bool = False` | Stop when LLM output contains the text. |
| `StopMessageTermination` | `stop_message: str = "TERMINATE"` | Stop when LLM output exactly matches the signal (after stripping whitespace). |
| `MaxMessageTermination` | `max_messages: int` | Stop after N messages in conversation. |
| `TokenUsageTermination` | `max_total_tokens`, `max_prompt_tokens`, `max_completion_tokens` | Stop when cumulative token usage exceeds budget. At least one limit required. |

---

## Handoff Conditions

Used with `strategy="swarm"` to define automatic agent transitions.

```python
from agentspan.agents.handoff import OnToolResult, OnTextMention, OnCondition

agent = Agent(
    ...,
    strategy="swarm",
    handoffs=[
        OnToolResult(tool_name="escalate", target="supervisor"),
        OnTextMention(text="transfer to billing", target="billing"),
        OnCondition(condition=lambda ctx: ctx["iteration"] > 5, target="summarizer"),
    ],
)
```

| Condition | Parameters | Description |
|-----------|-----------|-------------|
| `OnToolResult` | `tool_name: str`, `target: str`, `result_contains: str = None` | Hand off after a specific tool is called. Optionally filter by result content. |
| `OnTextMention` | `text: str`, `target: str` | Hand off when LLM output contains text (case-insensitive). |
| `OnCondition` | `condition: Callable`, `target: str` | Hand off when custom callable returns `True`. Context has `result`, `tool_name`, `tool_result`, `messages`. |

---

## Code Execution

### Quick Setup

```python
agent = Agent(
    ...,
    local_code_execution=True,
    allowed_languages=["python", "bash"],
    allowed_commands=["pip", "ls"],
)
```

### Full Control

```python
from agentspan.agents.code_execution_config import CodeExecutionConfig
from agentspan.agents.code_executor import DockerCodeExecutor

agent = Agent(
    ...,
    code_execution=CodeExecutionConfig(
        executor=DockerCodeExecutor(image="python:3.12-slim", timeout=60),
        allowed_languages=["python"],
        allowed_commands=["pip"],
    ),
)
```

#### CodeExecutionConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Whether code execution is active. |
| `allowed_languages` | `list[str]` | `["python"]` | Languages the LLM may use. |
| `allowed_commands` | `list[str]` | `[]` | Shell commands code may invoke. Empty = no restrictions. |
| `executor` | `CodeExecutor` | `None` | Executor backend. `None` creates `LocalCodeExecutor`. |
| `timeout` | `int` | `30` | Max execution time in seconds. |
| `working_dir` | `str` | `None` | Working directory. |

#### Executor Types

| Executor | Key Parameters | Description |
|----------|---------------|-------------|
| `LocalCodeExecutor` | `language`, `timeout`, `working_dir` | Local subprocess (no sandboxing). |
| `DockerCodeExecutor` | `image`, `network_enabled`, `memory_limit`, `volumes` | Docker container (sandboxed). |
| `JupyterCodeExecutor` | `kernel_name`, `startup_code` | Jupyter kernel (persistent state). |
| `ServerlessCodeExecutor` | `endpoint`, `api_key`, `headers` | Remote HTTP execution service. |

#### CodeExecutor.as_tool()

Any executor can be used as a standalone tool via `as_tool()`:

```python
from agentspan.agents.code_executor import DockerCodeExecutor

executor = DockerCodeExecutor(image="python:3.12-slim", timeout=30)

agent = Agent(
    name="coder",
    model="openai/gpt-4o",
    tools=[executor.as_tool()],
    instructions="Write and execute Python code to solve problems.",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `"execute_code"` | Override tool name. |
| `description` | `str` | auto | Override description. |

This is an alternative to `CodeExecutionConfig` — it gives direct control over which executor to use without the `code_execution` parameter.

---

## Prompt Templates

Reference server-side prompt templates instead of inline instructions.

```python
from agentspan.agents import PromptTemplate

agent = Agent(
    name="my_agent",
    model="openai/gpt-4o",
    instructions=PromptTemplate(
        name="customer_support_v2",
        variables={"company": "Acme Corp", "tone": "friendly"},
        version=3,
    ),
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | **required** | Name of the prompt template on the Conductor server. |
| `variables` | `dict` | `{}` | Substitution variables for `${var}` placeholders. Values may include Conductor expressions. |
| `version` | `int` | `None` | Template version. `None` means latest. |

---

## Runtime

### AgentRuntime

```python
from agentspan.agents import AgentRuntime

with AgentRuntime(server_url="http://localhost:6767/api") as runtime:
    result = runtime.run(agent, "Hello!")
```

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server_url` | `str` | `None` | Conductor server URL. Overrides env/config. |
| `api_key` | `str` | `None` | Auth key. Overrides env/config. |
| `api_secret` | `str` | `None` | Auth secret. Overrides env/config. |
| `config` | `AgentConfig` | `None` | Full runtime configuration. Explicit keyword params take precedence. |

#### Execution Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run(agent, prompt, *, media, session_id, idempotency_key)` | `AgentResult` | Synchronous execution. Blocks until complete. |
| `start(agent, prompt, *, media, session_id, idempotency_key)` | `AgentHandle` | Async fire-and-forget. Returns handle for polling/interaction. |
| `stream(agent, prompt, *, media, session_id)` | `Iterator[AgentEvent]` | Event-based streaming. Yields events as they occur. |
| `run_async(agent, prompt, *, media, session_id, idempotency_key)` | `AgentResult` | Async execution (awaitable). |
| `plan(agent)` | `WorkflowDef` | Compile without executing. Returns agent definition. |

Common parameters for execution methods:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `Agent` | **required** | The agent to execute. |
| `prompt` | `str` | **required** | User prompt. |
| `media` | `list[str]` | `None` | List of media URLs (images, audio, video) for multimodal input. |
| `session_id` | `str` | `None` | Session ID for conversation continuity. |
| `idempotency_key` | `str` | `None` | Prevents duplicate executions with the same key. |

#### Interaction Methods

| Method | Description |
|--------|-------------|
| `get_status(execution_id)` | Get current execution status. |
| `respond(execution_id, output)` | Complete a pending human task with arbitrary output. |
| `approve(execution_id)` | Approve a pending human-in-the-loop task. |
| `reject(execution_id, reason)` | Reject a pending task. |
| `send_message(execution_id, message)` | Send a message to a waiting agent. |
| `pause(execution_id)` | Pause an execution. |
| `resume(execution_id)` | Resume a paused execution. |
| `cancel(execution_id, reason)` | Cancel an execution. |
| `shutdown()` | Gracefully shut down runtime and workers. |

### AgentConfig

```python
from agentspan.agents import AgentConfig

config = AgentConfig(
    server_url="http://localhost:6767/api",
    auth_key="key",
    auth_secret="secret",
    default_timeout_seconds=0,
    llm_retry_count=3,
)

# Or load from AGENTSPAN_* env vars:
config = AgentConfig.from_env()
```

| Field | Type | Default | Env Variable | Description |
|-------|------|---------|-------------|-------------|
| `server_url` | `str` | `""` | `AGENTSPAN_SERVER_URL` | Agentspan server API URL. |
| `auth_key` | `str` | `None` | `AGENTSPAN_AUTH_KEY` | Auth key. |
| `auth_secret` | `str` | `None` | `AGENTSPAN_AUTH_SECRET` | Auth secret. |
| `default_timeout_seconds` | `int` | `0` | `AGENTSPAN_AGENT_TIMEOUT` | Default execution timeout. `0` = no timeout. |
| `llm_retry_count` | `int` | `3` | `AGENTSPAN_LLM_RETRY_COUNT` | LLM task retry count. |
| `worker_poll_interval_ms` | `int` | `100` | `AGENTSPAN_WORKER_POLL_INTERVAL` | Worker polling interval (ms). |
| `worker_thread_count` | `int` | `1` | `AGENTSPAN_WORKER_THREADS` | Threads per worker. |
| `auto_start_workers` | `bool` | `True` | `AGENTSPAN_AUTO_START_WORKERS` | Auto-start worker processes. |
| `auto_start_server` | `bool` | `True` | `AGENTSPAN_AUTO_START_SERVER` | Auto-start local server when URL points to localhost. |
| `daemon_workers` | `bool` | `True` | `AGENTSPAN_DAEMON_WORKERS` | Workers are daemon threads (killed on exit). |
| `auto_register_integrations` | `bool` | `False` | `AGENTSPAN_INTEGRATIONS_AUTO_REGISTER` | Auto-create LLM integrations on server. |
| `streaming_enabled` | `bool` | `True` | `AGENTSPAN_STREAMING_ENABLED` | Enable SSE streaming. |

---

## Result & Event Types

### AgentResult

Returned by `run()` and `run_async()`.

```python
from agentspan.agents import AgentResult

result = runtime.run(agent, "Hello!")
print(result.output)           # Final answer (str or structured type)
print(result.execution_id)     # Execution ID
print(result.status)           # "COMPLETED", "FAILED", etc.
print(result.messages)         # Full conversation history
print(result.tool_calls)       # All tool invocations
print(result.token_usage)      # TokenUsage object
print(result.finish_reason)    # LLM finish reason
result.print_result()          # Pretty-print output with metadata
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output` | `Any` | `None` | The agent's final answer. If `output_type` was set, a validated instance of that type. |
| `execution_id` | `str` | `""` | Execution ID (for debugging in the UI). |
| `correlation_id` | `str` | `None` | Correlation ID if provided at execution time. |
| `messages` | `list[dict]` | `[]` | Full conversation history (list of message dicts). |
| `tool_calls` | `list[dict]` | `[]` | All tool invocations with inputs and outputs. |
| `status` | `str` | `"COMPLETED"` | Terminal status: `"COMPLETED"`, `"FAILED"`, `"TERMINATED"`, `"TIMED_OUT"`. |
| `token_usage` | `TokenUsage` | `None` | Aggregated token usage across all LLM calls. |
| `metadata` | `dict` | `{}` | Extra data from the execution. |
| `finish_reason` | `str` | `None` | LLM finish reason (e.g. `"stop"`, `"LENGTH"`). |

Methods:
- `print_result()` — Pretty-prints output, tool call count, token usage, finish reason, and execution ID.

### TokenUsage

```python
from agentspan.agents import TokenUsage

if result.token_usage:
    print(result.token_usage.prompt_tokens)
    print(result.token_usage.completion_tokens)
    print(result.token_usage.total_tokens)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `prompt_tokens` | `int` | `0` | Total input/prompt tokens consumed. |
| `completion_tokens` | `int` | `0` | Total output/completion tokens generated. |
| `total_tokens` | `int` | `0` | Sum of prompt + completion tokens. |

### AgentHandle

Returned by `start()`. Allows monitoring and interacting with a running agent from any process.

```python
from agentspan.agents import AgentHandle

handle = runtime.start(agent, "Analyze reports")
print(handle.execution_id)

# Check status
status = handle.get_status()
if status.is_waiting:
    handle.approve()         # approve pending human task
    # handle.reject("reason")
    # handle.send("user message")
    # handle.respond({"key": "value"})

# Execution control
handle.pause()
handle.resume()
handle.cancel("no longer needed")
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_status()` | `AgentStatus` | Fetch current execution status. |
| `respond(output)` | — | Complete a pending human task with arbitrary output dict. |
| `approve()` | — | Approve a pending human-in-the-loop task. |
| `reject(reason)` | — | Reject a pending task with optional reason. |
| `send(message)` | — | Send a message to a waiting agent (multi-turn). |
| `pause()` | — | Pause the execution. |
| `resume()` | — | Resume a paused execution. |
| `cancel(reason)` | — | Cancel the execution with optional reason. |

### AgentStatus

Returned by `handle.get_status()` or `runtime.get_status(execution_id)`.

```python
status = handle.get_status()
if status.is_complete:
    print(status.output)
elif status.is_waiting:
    print(status.pending_tool)   # tool awaiting approval
elif status.is_running:
    print(status.current_task)   # currently executing task
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `execution_id` | `str` | `""` | Execution ID. |
| `is_complete` | `bool` | `False` | `True` if the execution has reached a terminal state. |
| `is_running` | `bool` | `False` | `True` if the execution is still executing. |
| `is_waiting` | `bool` | `False` | `True` if paused (e.g. human-in-the-loop). |
| `output` | `Any` | `None` | Available when `is_complete` is `True`. |
| `status` | `str` | `""` | Raw Conductor status string. |
| `current_task` | `str` | `None` | Reference name of the currently executing task. |
| `messages` | `list[dict]` | `[]` | Conversation messages accumulated so far. |
| `pending_tool` | `dict` | `None` | Tool call awaiting human approval (if `is_waiting`). |

### AgentEvent and EventType

Yielded by `stream()`. Each event represents a step in the agent's execution.

```python
from agentspan.agents import EventType

for event in runtime.stream(agent, "Hello"):
    if event.type == EventType.TOOL_CALL:
        print(f"Calling {event.tool_name} with {event.args}")
    elif event.type == EventType.TOOL_RESULT:
        print(f"{event.tool_name} returned: {event.result}")
    elif event.type == EventType.MESSAGE:
        print(event.content)
    elif event.type == EventType.HANDOFF:
        print(f"Handing off to {event.target}")
    elif event.type == EventType.DONE:
        print(f"Final: {event.output}")
```

#### EventType Enum

| Value | Description |
|-------|-------------|
| `THINKING` | Agent is processing (LLM call in progress). |
| `TOOL_CALL` | Agent is invoking a tool. `tool_name` and `args` are set. |
| `TOOL_RESULT` | Tool returned a result. `tool_name` and `result` are set. |
| `HANDOFF` | Agent is handing off to another agent. `target` is set. |
| `WAITING` | Execution is paused for human input. |
| `MESSAGE` | Agent produced a text response. `content` is set. |
| `ERROR` | An error occurred. `content` has the error message. |
| `DONE` | Execution complete. `output` has the final result. |
| `GUARDRAIL_PASS` | A guardrail check passed. `guardrail_name` is set. |
| `GUARDRAIL_FAIL` | A guardrail check failed. `guardrail_name` and `content` are set. |

#### AgentEvent Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Event type (see EventType enum). |
| `content` | `str` | Text content (for `THINKING`, `MESSAGE`, `ERROR`, `GUARDRAIL_PASS/FAIL`). |
| `tool_name` | `str` | Tool name (for `TOOL_CALL`, `TOOL_RESULT`). |
| `args` | `dict` | Tool arguments (for `TOOL_CALL`). |
| `result` | `Any` | Tool result (for `TOOL_RESULT`) or final output (for `DONE`). |
| `target` | `str` | Target agent name (for `HANDOFF`). |
| `output` | `Any` | Final output (for `DONE`). |
| `execution_id` | `str` | Execution ID. |
| `guardrail_name` | `str` | Guardrail name (for `GUARDRAIL_PASS/FAIL`). |

---

## Extended Agent Types

### UserProxyAgent

A human stand-in agent. When it's this agent's turn, the execution pauses with a `HumanTask` and waits for real human input. Useful in multi-agent conversations where a human participates.

```python
from agentspan.agents import UserProxyAgent, Agent

user = UserProxyAgent(name="human")
assistant = Agent(name="assistant", model="openai/gpt-4o")

team = Agent(
    name="chat",
    model="openai/gpt-4o",
    agents=[user, assistant],
    strategy="round_robin",
    max_turns=6,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `"user"` | Agent name. |
| `human_input_mode` | `str` | `"ALWAYS"` | When to request human input: `"ALWAYS"`, `"TERMINATE"`, or `"NEVER"`. |
| `default_response` | `str` | `"Continue."` | Response when `human_input_mode="NEVER"` (pass-through). |
| `model` | `str` | `"openai/gpt-4o"` | LLM model (only used when generating a fallback response). |
| `instructions` | `str \| Callable` | auto | System prompt. Defaults to relaying human input exactly. |

### GPTAssistantAgent

Wraps an OpenAI Assistant (with its own instructions, tools, and file search) as a Conductor Agent.

```python
from agentspan.agents import GPTAssistantAgent

# Use an existing assistant
agent = GPTAssistantAgent(
    name="coder",
    assistant_id="asst_abc123",
)

# Or create one on the fly
agent = GPTAssistantAgent(
    name="analyst",
    model="gpt-4o",
    instructions="You are a data analyst.",
    openai_tools=[{"type": "code_interpreter"}],
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | **required** | Agent name. |
| `assistant_id` | `str` | `None` | Existing OpenAI Assistant ID. If `None`, creates a new assistant. |
| `model` | `str` | `"openai/gpt-4o"` | OpenAI model. Only used when creating a new assistant. |
| `instructions` | `str` | `""` | System instructions for the assistant. |
| `openai_tools` | `list[dict]` | `None` | OpenAI-native tools config (e.g. `[{"type": "code_interpreter"}]`). |
| `api_key` | `str` | `None` | OpenAI API key. Falls back to `OPENAI_API_KEY` env var. |

Requires the `openai` package (`pip install openai`).

---

## Convenience Functions

Top-level functions that use a shared singleton `AgentRuntime`. Useful for scripts; for production, prefer creating an `AgentRuntime` explicitly.

```python
from agentspan.agents import run, start, stream, run_async, plan, shutdown
```

| Function | Returns | Description |
|----------|---------|-------------|
| `run(agent, prompt, **kwargs)` | `AgentResult` | Synchronous execution. Blocks until complete. |
| `start(agent, prompt, **kwargs)` | `AgentHandle` | Async fire-and-forget. Returns handle immediately. |
| `stream(agent, prompt, **kwargs)` | `Iterator[AgentEvent]` | Yields events as they occur. |
| `run_async(agent, prompt, **kwargs)` | `AgentResult` | Async/await execution. |
| `plan(agent)` | `WorkflowDef` | Compile without executing. Returns agent definition. |
| `shutdown()` | — | Explicitly shut down the singleton runtime and workers. |

All execution functions accept `media`, `session_id`, `idempotency_key`, and `runtime` keyword arguments (same as `AgentRuntime` methods).
