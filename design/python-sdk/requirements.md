# Conductor Agents SDK — Requirements

## 1. Overview

The `agentspan-sdk` Python SDK enables developers to build AI agents backed by durable executions. Agents survive process crashes, tools scale as distributed workers, and human-in-the-loop approvals can pause for days.

### Target Users

- Python developers building AI-powered applications
- Teams needing production-grade agent orchestration (not just prototyping)
- Organizations already using Conductor for workflow orchestration

### Key Differentiators vs. Other Agent SDKs

| Requirement | OpenAI Agents SDK | LangGraph | CrewAI | **Conductor Agents** |
|---|---|---|---|---|
| Durability (crash recovery) | No | No | No | **Yes** (execution-backed) |
| Cross-process control | No | No | No | **Yes** (AgentHandle) |
| Human approval (days) | No | Limited | Limited | **Yes** (native WaitTask) |
| Visual debugging | No | LangSmith | No | **Yes** (Conductor UI) |
| Tool scaling | In-process | In-process | In-process | **Distributed workers** |
| Server-side tools | No | No | No | **Yes** (HTTP, MCP) |

---

## 2. Functional Requirements

### 2.1 Agent Definition

| ID | Requirement | Status |
|---|---|---|
| FR-01 | Single `Agent` class for all patterns (single, multi, nested) | Done |
| FR-02 | `"provider/model"` format for LLM specification | Done |
| FR-03 | Static or dynamic (callable) system prompt | Done |
| FR-04 | Configurable max_turns, max_tokens, temperature | Done |
| FR-05 | Structured output via Pydantic `output_type` | Done |
| FR-06 | Arbitrary metadata attachment | Done |
| FR-07 | `>>` operator for sequential pipelines | Done |
| FR-08 | `stop_when` callable for early loop termination | Done |
| FR-09 | `memory` parameter for ConversationMemory integration | Done |
| FR-10 | `dependencies` parameter for tool dependency injection | Done |

### 2.2 Tool System

| ID | Requirement | Status |
|---|---|---|
| FR-11 | `@tool` decorator: Python function -> Conductor task definition | Done |
| FR-12 | JSON Schema auto-generation from type hints | Done |
| FR-13 | `approval_required` flag for human-in-the-loop | Done |
| FR-14 | `timeout_seconds` per-tool timeout | Done |
| FR-15 | `http_tool()`: HTTP endpoints as server-side tools | Done |
| FR-16 | `mcp_tool()`: MCP server tools (discovered at runtime) | Done |
| FR-17 | Mixed tool types in a single agent | Done |
| FR-18 | `ToolContext` injection for tools that declare `context` parameter | Done |
| FR-19 | `@worker_task` compatibility (existing Conductor workers as tools) | Done |
| FR-20 | Circuit breaker: disable tools after 3 consecutive failures | Done |
| FR-21 | Robust LLM response parsing (markdown fences, variant keys, embedded JSON) | Done |

### 2.3 Execution API

| ID | Requirement | Status |
|---|---|---|
| FR-22 | `run()`: Synchronous blocking execution | Done |
| FR-23 | `start()`: Async fire-and-forget with AgentHandle | Done |
| FR-24 | `stream()`: Real-time event streaming | Done |
| FR-25 | `run_async()`: Awaitable async execution | Done |
| FR-26 | Singleton runtime (shared across calls) | Done |
| FR-27 | Custom runtime parameter for isolation | Done |
| FR-28 | `session_id` for multi-turn conversation continuity | Done |
| FR-29 | `idempotency_key` for duplicate prevention | Done |

### 2.4 Result Types

| ID | Requirement | Status |
|---|---|---|
| FR-30 | `AgentResult`: output, execution_id, messages, tool_calls, status | Done |
| FR-31 | `AgentHandle`: get_status, approve, reject, send, pause, resume, cancel | Done |
| FR-32 | `AgentStatus`: is_complete, is_running, is_waiting, output | Done |
| FR-33 | `AgentEvent`: typed events (THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING, MESSAGE, ERROR, DONE) | Done |

### 2.5 Multi-Agent Strategies

| ID | Requirement | Status |
|---|---|---|
| FR-34 | Handoff: LLM-based routing to sub-agents via SwitchTask | Done |
| FR-35 | Sequential: chain of SubWorkflowTask calls | Done |
| FR-36 | Parallel: ForkTask + JoinTask for concurrent execution | Done |
| FR-37 | Router (Agent-based): use router agent's model/instructions | Done |
| FR-38 | Router (Function-based): callable registered as worker task | Done |
| FR-39 | Hybrid: agent with both tools AND sub-agents | Done |
| FR-40 | Hierarchical: nested agents to arbitrary depth | Done |

### 2.6 Guardrails

| ID | Requirement | Status |
|---|---|---|
| FR-41 | `Guardrail` class with func, position, on_fail, name | Done |
| FR-42 | Input guardrails: validate before LLM call | Done |
| FR-43 | Output guardrails: validate after LLM response | Done |
| FR-44 | `on_fail="retry"`: re-execute with feedback | Done |
| FR-45 | `on_fail="raise"`: fail execution immediately | Done |
| FR-46 | Compile guardrails into Conductor worker tasks | Done |

### 2.7 Memory

| ID | Requirement | Status |
|---|---|---|
| FR-47 | `ConversationMemory` dataclass with messages, max_messages, max_tokens | Done |
| FR-48 | Message trimming (preserves system messages) | Done |
| FR-49 | Pre-populated messages seed the conversation | Done |
| FR-50 | `max_messages` passed to dispatch for in-loop trimming | Done |

---

## 3. Non-Functional Requirements

### 3.1 Performance

| ID | Requirement | Status |
|---|---|---|
| NFR-01 | Singleton runtime: no new connections per call | Done |
| NFR-02 | Workers are long-lived (not started/stopped per call) | Done |
| NFR-03 | Compiled workflow caching (per agent.name) | Done |
| NFR-04 | Graceful shutdown via atexit handler | Done |

### 3.2 Reliability

| ID | Requirement | Status |
|---|---|---|
| NFR-05 | Circuit breaker for failing tools | Done |
| NFR-06 | Fuzzy JSON parsing handles LLM output variations | Done |
| NFR-07 | Configurable execution timeout (default 300s) | Done |
| NFR-08 | Configurable LLM retry count (default 3) | Done |

### 3.3 Observability

| ID | Requirement | Status |
|---|---|---|
| NFR-09 | Structured logging across all modules | Done |
| NFR-10 | Execution IDs for Conductor UI debugging | Done |
| NFR-11 | Streaming events for real-time monitoring | Done |
| NFR-12 | Tool call history in AgentResult.tool_calls | Done |

### 3.4 Usability

| ID | Requirement | Status |
|---|---|---|
| NFR-13 | 5-line hello world: Agent + run | Done |
| NFR-14 | Zero config for simple cases (env vars only) | Done |
| NFR-15 | Type hints on all public APIs | Done |
| NFR-16 | 15 progressive examples | Done |

### 3.5 Quality

| ID | Requirement | Status |
|---|---|---|
| NFR-17 | Unit tests: 152 tests, all passing | Done |
| NFR-18 | CI/CD: GitHub Actions (Python 3.9-3.13, ruff, mypy) | Done |
| NFR-19 | All 15 examples compile and execute successfully | Done |

---

## 4. Compatibility

### Python Versions

- Python 3.9+ required
- Tested on 3.9, 3.10, 3.11, 3.12, 3.13

### Dependencies

- `conductor-python>=1.1.10` (Conductor client SDK)
- `pydantic` (optional, for structured output)

### LLM Providers

Supported via Conductor's AI integrations:

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

---

## 5. Public API Surface

All exports from `agentspan.agents`:

```python
# Core
Agent

# Tools
tool, ToolDef, ToolContext, http_tool, mcp_tool

# Execution
run, run_async, start, stream

# Results
AgentResult, AgentHandle, AgentStatus, AgentEvent, EventType

# Guardrails
Guardrail, GuardrailResult, guardrail, GuardrailDef, OnFail, Position

# Memory
ConversationMemory
```

---

## 6. Conductor Primitives Used

| Conductor Primitive | SDK Usage |
|---|---|
| `ConductorWorkflow` | Each Agent compiles to one workflow |
| `LlmChatComplete` | LLM calls (system task, no worker needed) |
| `DoWhileTask` | Agent think-act-observe loop |
| `SetVariableTask` | Persist conversation messages in workflow variables |
| `SwitchTask` | Route to sub-agents (handoff, router) |
| `InlineSubWorkflowTask` | Execute sub-agent workflows |
| `ForkTask` + `JoinTask` | Parallel agent execution |
| `HttpTask` | HTTP tools (server-side) |
| `ListMcpTools` + `CallMcpTool` | MCP tool discovery and execution |
| `WaitTask` | Human-in-the-loop approval pauses |
| `@worker_task` | Register tool functions as distributed workers |
| `workflow.variables` | Conversation state persistence |
| `TimeoutPolicy` | Configurable execution timeouts |
