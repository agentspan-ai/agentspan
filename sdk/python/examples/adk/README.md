# Google ADK Examples

These examples demonstrate running agents written with [Google's Agent Development Kit (ADK)](https://github.com/google/adk-python) (`google-adk`) on the Conductor agent runtime.

The agents are defined using standard ADK classes — the Conductor runtime auto-detects the framework, serializes the agent generically, and the server normalizes the config into a Conductor workflow. **Zero translation code in the SDK.**

## Prerequisites

```bash
pip install google-adk agentspan-sdk
```

Configure via `.env` file in the project root (recommended):

```dotenv
AGENT_LLM_MODEL=openai/gpt-4o-mini
AGENTSPAN_SERVER_URL=http://localhost:8080/api
GOOGLE_GEMINI_API_KEY=your-key  # or configure via Conductor server
```

Or export environment variables directly:

```bash
export AGENT_LLM_MODEL=openai/gpt-4o-mini
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
export GOOGLE_GEMINI_API_KEY=your-key
```

## Examples

| # | File | Feature | Description |
|---|------|---------|-------------|
| 01 | [01_basic_agent.py](01_basic_agent.py) | **Basic Agent** | Simplest agent — single LLM, no tools. Shows auto-detection and server normalization. |
| 02 | [02_function_tools.py](02_function_tools.py) | **Function Tools** | Multiple Python functions as tools with typed params and docstrings. ADK auto-converts them. |
| 03 | [03_structured_output.py](03_structured_output.py) | **Structured Output** | Pydantic `output_schema` for enforced JSON responses. Combined with `generate_content_config`. |
| 04 | [04_sub_agents.py](04_sub_agents.py) | **Sub-Agents** | Multi-agent orchestration with coordinator → specialist routing via `sub_agents`. |
| 05 | [05_generation_config.py](05_generation_config.py) | **Generation Config** | `generate_content_config` for temperature and output token control. Creative vs. factual agents. |
| 06 | [06_streaming.py](06_streaming.py) | **Streaming** | Real-time SSE event streaming via `runtime.stream()`. Shows tool_call, tool_result, and done events. |
| 07 | [07_output_key_state.py](07_output_key_state.py) | **Output Key & State** | `output_key` for storing agent results in session state. Multi-agent data passing. |
| 08 | [08_instruction_templating.py](08_instruction_templating.py) | **Instruction Templating** | ADK's `{variable}` syntax in instructions for dynamic context injection from state. |
| 09 | [09_multi_tool_agent.py](09_multi_tool_agent.py) | **Multi-Tool Agent** | Complex tool orchestration with 4 tools (search, inventory, shipping, coupons). Best-practice dict returns. |
| 10 | [10_hierarchical_agents.py](10_hierarchical_agents.py) | **Hierarchical Agents** | Multi-level delegation: coordinator → team leads → specialists. Deep sub_agents nesting. |

## Feature Coverage

| Google ADK Feature | Example(s) |
|---|---|
| `Agent` class | All |
| Function tools (auto-converted) | 02, 04, 06, 07, 08, 09, 10 |
| `sub_agents` (multi-agent) | 04, 07, 10 |
| `output_schema` (structured output) | 03 |
| `generate_content_config` (temperature, tokens) | 03, 05 |
| `output_key` (state management) | 07 |
| `instruction` templating (`{var}`) | 08 |
| `description` (for agent routing) | 04, 10 |
| Streaming (`runtime.stream()`) | 06 |
| Multi-tool orchestration | 09 |
| Hierarchical sub-agents (3 levels) | 10 |

## How It Works

```
Google ADK Agent object
  │
  ▼  (auto-detected by type(agent).__module__.startswith("google.adk"))
Generic serializer → JSON dict + callable extraction
  │
  ▼  POST /api/agent/start { framework: "google_adk", rawConfig: {...} }
Server GoogleADKNormalizer → AgentConfig → Conductor WorkflowDef
  │
  ▼
Conductor runtime executes the workflow
```

## Key ADK Differences from OpenAI

| Concept | Google ADK | OpenAI Agents SDK |
|---|---|---|
| Instructions | `instruction` (singular) | `instructions` (plural) |
| Multi-agent | `sub_agents` | `handoffs` |
| Model config | `generate_content_config` dict | `ModelSettings` class |
| Structured output | `output_schema` | `output_type` |
| Tool definition | Plain Python functions | `@function_tool` decorator |
| State management | `output_key` + `{var}` templating | Context/Sessions |
