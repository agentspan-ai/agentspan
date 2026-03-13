# Examples

Runnable examples demonstrating every feature of the Conductor Agents SDK.

## Getting Started

### 1. Configure your environment

Create a `.env` file in the project root (recommended):

```dotenv
AGENT_LLM_MODEL=openai/gpt-4o-mini
AGENTSPAN_SERVER_URL=http://localhost:8080/api
#AGENTSPAN_AUTH_KEY=<key> # if authentication is enabled
#AGENTSPAN_AUTH_SECRET=<secret> # if authentication is enabled..
```

Or export environment variables directly:

```bash
export AGENT_LLM_MODEL=openai/gpt-4o-mini
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
#export AGENTSPAN_AUTH_KEY=<key> # if authentication is enabled
#export AGENTSPAN_AUTH_SECRET=<secret> # if authentication is enabled..
```

#### 1.1. Choose a model

The `AGENT_LLM_MODEL` variable uses the `provider/model-name` format. Examples:

| Provider | Model string |
|----------|-------------|
| OpenAI | `openai/gpt-4o-mini` (default) |
| Anthropic | `anthropic/claude-sonnet-4-20250514` |
| Google Gemini | `google_gemini/gemini-2.0-flash` |
| AWS Bedrock | `aws_bedrock/...` |
| Azure OpenAI | `azure_openai/...` |

All supported providers: `openai`, `anthropic`, `google_gemini`, `google_vertex_ai`,
`azure_openai`, `aws_bedrock`, `cohere`, `mistral`, `groq`, `perplexity`,
`hugging_face`, `deepseek`.

### 3. Run an example

```bash
python examples/01_basic_agent.py
python examples/15_agent_discussion.py
```

Some examples have additional dependencies noted in their headers.

---

## Basic Examples

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 01 | [Basic Agent](01_basic_agent.py) | Simplest possible agent — single LLM, no tools, 5 lines of code |
| 02 | [Tools](02_tools.py) | Multiple `@tool` functions, approval-required tools |

## Tool Calling

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 02a | [Simple Tools](02a_simple_tools.py) | Two tools (weather, stocks) — LLM picks the right one |
| 02b | [Multi-Step Tools](02b_multi_step_tools.py) | Chained tool calls: lookup → fetch → calculate → answer |
| 03 | [Structured Output](03_structured_output.py) | Pydantic `output_type` for typed, validated responses |
| 04 | [HTTP & MCP Tools](04_http_and_mcp_tools.py) | Server-side tools via `http_tool()` and `mcp_tool()` — no workers needed |
| 04b | [MCP Weather](04_mcp_weather.py) | Real-time weather via an MCP server |
| 14 | [Existing Workers](14_existing_workers.py) | Use existing `@worker_task` functions directly as agent tools |
| 33 | [Single Turn Tool](33_single_turn_tool.py) | Single-turn tool invocation with immediate response |
| 33 | [External Workers](33_external_workers.py) | Reference workers in other services via `@tool(external=True)` — no local code needed |

## Multi-Agent Orchestration

| # | Example | Pattern | Key API |
|---|---------|---------|---------|
| 05 | [Handoffs](05_handoffs.py) | LLM-driven delegation to sub-agents | `strategy="handoff"` |
| 06 | [Sequential Pipeline](06_sequential_pipeline.py) | Agents run in order, output chains forward | `strategy="sequential"`, `>>` operator |
| 07 | [Parallel Agents](07_parallel_agents.py) | All agents run concurrently, results aggregated | `strategy="parallel"` |
| 08 | [Router Agent](08_router_agent.py) | Router (Agent or callable) selects which sub-agent runs | `strategy="router"` |
| 13 | [Hierarchical Agents](13_hierarchical_agents.py) | 3-level nested hierarchy: CEO → leads → specialists | Nested `strategy="handoff"` |
| 15 | [Agent Discussion](15_agent_discussion.py) | Round-robin debate between agents, piped to a summarizer | `strategy="round_robin"`, `>>` |
| 16 | [Random Strategy](16_random_strategy.py) | Random agent selected each turn (brainstorming) | `strategy="random"` |
| 17 | [Swarm Orchestration](17_swarm_orchestration.py) | Automatic transitions via handoff conditions | `strategy="swarm"`, `OnTextMention` |
| 18 | [Manual Selection](18_manual_selection.py) | Human picks which agent speaks each turn | `strategy="manual"` |
| 20 | [Constrained Transitions](20_constrained_transitions.py) | Restrict which agents can follow which | `allowed_transitions` |
| 29 | [Agent Introductions](29_agent_introductions.py) | Agents introduce themselves before a group discussion | `introduction` parameter |
| 38 | [Tech Trends](38_tech_trends.py) | Multi-agent research pipeline with live HTTP API tools | `>>` operator, `from __future__ import annotations` |

## Human-in-the-Loop

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 09 | [Human-in-the-Loop](09_human_in_the_loop.py) | Tool approval gate — approve or reject before execution | `approval_required=True` |
| 09b | [HITL with Feedback](09b_hitl_with_feedback.py) | Custom feedback via `respond()` — editorial review with revision notes | `handle.respond()` |
| 09c | [HITL with Streaming](09c_hitl_streaming.py) | Real-time event stream with approval pauses | `stream()` + `approve()` |
| 27 | [User Proxy Agent](27_user_proxy_agent.py) | Human stand-in agent for interactive conversations | `UserProxyAgent` |

## Guardrails & Safety

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 10 | [Guardrails](10_guardrails.py) | Output validation with `@guardrail` decorator, `OnFail`/`Position` enums | `@guardrail`, `OnFail`, `Position` |
| 21 | [Regex Guardrails](21_regex_guardrails.py) | Pattern-based blocking (emails, SSNs) and allow-listing (JSON) | `RegexGuardrail` |
| 22 | [LLM Guardrails](22_llm_guardrails.py) | AI-powered content safety evaluation via a judge LLM | `LLMGuardrail` |
| 31 | [Tool Guardrails](31_tool_guardrails.py) | Pre-execution validation on tool inputs (SQL injection blocking) | `@tool(guardrails=[...])` |
| 32 | [Human Guardrail](32_human_guardrail.py) | Pause workflow for human review when output fails validation | `on_fail="human"` |
| 35 | [Standalone Guardrails](35_standalone_guardrails.py) | Use `@guardrail` as plain callables — no agent, no server needed | `@guardrail`, `GuardrailResult` |
| 36 | [Simple Agent Guardrails](36_simple_agent_guardrails.py) | Guardrails on agents without tools — mixed regex (InlineTask) + custom (worker) | `RegexGuardrail`, `@guardrail` |
| 37 | [Fix Guardrail](37_fix_guardrail.py) | Auto-correct output instead of retrying — deterministic fixes | `on_fail="fix"`, `fixed_output` |

## Termination Conditions

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 19 | [Composable Termination](19_composable_termination.py) | Text mention, stop message, max messages, token budget, AND/OR composition | `TextMentionTermination`, `&`, `\|` |

## Code Execution

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 24 | [Code Execution](24_code_execution.py) | Local, Docker, Jupyter, and serverless code execution sandboxes | `LocalCodeExecutor`, `DockerCodeExecutor` |

## Memory

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 25 | [Semantic Memory](25_semantic_memory.py) | Long-term memory with similarity-based retrieval across sessions | `SemanticMemory` |

## Observability

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 23 | [Token Tracking](23_token_tracking.py) | Per-run token usage and cost estimation | `result.token_usage` |
| 26 | [OpenTelemetry Tracing](26_opentelemetry_tracing.py) | Industry-standard OTel spans for runs, tools, and handoffs | `tracing` module |

## Execution Modes

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 11 | [Streaming](11_streaming.py) | Real-time events via `runtime.stream()` | `AgentEvent`, `EventType` |
| 12 | [Long-Running](12_long_running.py) | Fire-and-forget with status polling from any process | `runtime.start()`, `handle.get_status()` |

## Multimodal

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 30 | [Multimodal Agent](30_multimodal_agent.py) | Image/video analysis with vision models via the `media` parameter | `media=["url"]` |

## Prompt Templates

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 34 | [Prompt Templates](34_prompt_templates.py) | Reusable, versioned prompts stored on the server for instructions and user prompts | `PromptTemplate` |

## Integrations

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 28 | [GPT Assistant Agent](28_gpt_assistant_agent.py) | Wrap OpenAI Assistants API (with code interpreter) as a Conductor agent | `GPTAssistantAgent` |

---

## Troubleshooting

### SSL Certificate Errors on macOS

Examples that make outbound HTTPS calls (e.g., `38_tech_trends.py`) may fail with:
```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

This happens because macOS Python framework installs do not link to system certificates.
Fix by running (once per Python installation):

```bash
# Replace 3.12 with your Python version
/Applications/Python\ 3.12/Install\ Certificates.command
```

### PEP 563 Compatibility

Tool functions defined in modules that use `from __future__ import annotations` work
correctly. The SDK resolves string annotations to real types at registration time.

## Feature Index

Quick lookup — find the right example for any SDK feature:

| Feature | Example(s) |
|---------|-----------|
| `Agent` | 01 |
| `@tool` decorator | 02, 02a, 02b |
| `http_tool()` | 04 |
| `mcp_tool()` | 04, 04b |
| `output_type` (Pydantic) | 03 |
| `strategy="handoff"` | 05, 13 |
| `strategy="sequential"`, `>>` | 06, 15 |
| `strategy="parallel"` | 07 |
| `strategy="router"` | 08 |
| `strategy="round_robin"` | 15, 20, 29 |
| `strategy="random"` | 16 |
| `strategy="swarm"` | 17 |
| `strategy="manual"` | 18 |
| `allowed_transitions` | 20 |
| `introduction` | 29 |
| `approval_required=True` | 02, 09 |
| `handle.approve()` / `reject()` | 09 |
| `handle.respond()` / `send()` | 09b, 27 |
| `runtime.stream()` | 09c, 11 |
| `runtime.start()` | 12, 18, 27 |
| `@guardrail` decorator | 10, 35 |
| `Guardrail` | 10, 32 |
| `OnFail` / `Position` enums | 10 |
| `RegexGuardrail` | 21 |
| `LLMGuardrail` | 22 |
| `on_fail="fix"` | 37 |
| `on_fail="human"` | 32 |
| `fixed_output` | 37 |
| `@tool(guardrails=[...])` | 31 |
| `TextMentionTermination` | 19 |
| `StopMessageTermination` | 19 |
| `MaxMessageTermination` | 19 |
| `TokenUsageTermination` | 19 |
| `&` / `\|` (composable) | 19 |
| `LocalCodeExecutor` | 24 |
| `DockerCodeExecutor` | 24 |
| `JupyterCodeExecutor` | 24 |
| `ServerlessCodeExecutor` | 24 |
| `SemanticMemory` | 25 |
| `TokenUsage` | 23 |
| OpenTelemetry tracing | 26 |
| `UserProxyAgent` | 27 |
| `GPTAssistantAgent` | 28 |
| `@worker_task` as tools | 14 |
| `@tool(external=True)` | 33 |
| `OnTextMention` / `OnToolResult` | 17 |
| `media` (multimodal input) | 30 |
| `PromptTemplate` | 34 |
| `from __future__ import annotations` | 38 |
