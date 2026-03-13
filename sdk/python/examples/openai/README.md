# OpenAI Agent SDK Examples

These examples demonstrate running agents written with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (`openai-agents`) on the Conductor agent runtime.

The agents are defined using standard OpenAI SDK classes and decorators — the Conductor runtime auto-detects the framework, serializes the agent generically, and the server normalizes the config into a Conductor workflow. **Zero translation code in the SDK.**

## Prerequisites

```bash
pip install openai-agents agentspan-sdk
```

Configure via `.env` file in the project root (recommended):

```dotenv
AGENT_LLM_MODEL=openai/gpt-4o-mini
AGENTSPAN_SERVER_URL=http://localhost:8080/api
OPENAI_API_KEY=your-key  # or configure via Conductor server
```

Or export environment variables directly:

```bash
export AGENT_LLM_MODEL=openai/gpt-4o-mini
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
export OPENAI_API_KEY=your-key
```

## Examples

| # | File | Feature | Description |
|---|------|---------|-------------|
| 01 | [01_basic_agent.py](01_basic_agent.py) | **Basic Agent** | Simplest agent — single LLM, no tools. Shows auto-detection and server normalization. |
| 02 | [02_function_tools.py](02_function_tools.py) | **Function Tools** | Multiple `@function_tool` decorated functions with typed parameters. Tools are auto-extracted as Conductor workers. |
| 03 | [03_structured_output.py](03_structured_output.py) | **Structured Output** | Pydantic `output_type` for enforced JSON schema responses. Combined with `ModelSettings`. |
| 04 | [04_handoffs.py](04_handoffs.py) | **Handoffs** | Multi-agent orchestration with triage → specialist handoffs. Maps to Conductor's `strategy="handoff"`. |
| 05 | [05_guardrails.py](05_guardrails.py) | **Guardrails** | Input guardrails (PII detection) and output guardrails (safety filtering). Guardrail functions become Conductor workers. |
| 06 | [06_model_settings.py](06_model_settings.py) | **Model Settings** | `ModelSettings` for temperature and max_tokens tuning. Creative vs. precise agents. |
| 07 | [07_streaming.py](07_streaming.py) | **Streaming** | Real-time SSE event streaming via `runtime.stream()`. Shows tool_call, tool_result, and done events. |
| 08 | [08_agent_as_tool.py](08_agent_as_tool.py) | **Agent-as-Tool** | Manager pattern with `Agent.as_tool()`. Manager retains control and synthesizes specialist results. |
| 09 | [09_dynamic_instructions.py](09_dynamic_instructions.py) | **Dynamic Instructions** | Callable instruction function that generates context-aware prompts (time-of-day, user preferences). |
| 10 | [10_multi_model.py](10_multi_model.py) | **Multi-Model** | Multiple agents with shared `settings.llm_model`. Override via `AGENT_LLM_MODEL` env var. |

## Feature Coverage

| OpenAI SDK Feature | Example(s) |
|---|---|
| `Agent` class | All |
| `@function_tool` decorator | 02, 04, 05, 07, 08, 09, 10 |
| `handoffs` | 04, 10 |
| `output_type` (structured output) | 03 |
| `ModelSettings` (temperature, max_tokens) | 03, 06, 10 |
| `InputGuardrail` / `OutputGuardrail` | 05 |
| `Agent.as_tool()` (manager pattern) | 08 |
| Dynamic instructions (callable) | 09 |
| Multiple models | 10 |
| Streaming (`runtime.stream()`) | 07 |
| Multi-agent patterns | 04, 08, 10 |

## How It Works

```
OpenAI Agent object
  │
  ▼  (auto-detected by type(agent).__module__ == "agents")
Generic serializer → JSON dict + callable extraction
  │
  ▼  POST /api/agent/start { framework: "openai", rawConfig: {...} }
Server OpenAINormalizer → AgentConfig → Conductor WorkflowDef
  │
  ▼
Conductor runtime executes the workflow
```
