# LangChain → AgentSpan Integration

How LangChain agents are translated and executed through the AgentSpan platform.

## Overview

Modern LangChain (v1.2+) uses `create_agent()` from `langchain.agents`, which returns a `CompiledStateGraph`. AgentSpan detects this as a LangGraph object and routes it through the LangGraph serialization pipeline. This means LangChain agents get the same server-side LLM orchestration, tool extraction, and system prompt support as native LangGraph agents.

Legacy `AgentExecutor` objects (deprecated in LangChain v1.2) have a separate passthrough path, but `AgentExecutor` is no longer importable from current LangChain versions.

### How It Works

```
create_agent(llm, tools=[...], system_prompt="...")
    │
    ▼
CompiledStateGraph  ──detect_framework()──► "langgraph"
    │
    ▼
serialize_langgraph()
    ├─ _find_model_in_graph()           → "openai/gpt-4o-mini"
    ├─ _find_tools_in_graph()           → [tool1, tool2, ...]
    ├─ _extract_system_prompt_from_graph() → "You are a helpful assistant."
    │
    ▼
Full Extraction raw_config:
    { name, model, instructions, tools: [...] }
    │
    ▼
Server: LangGraphNormalizer → AgentCompiler → Conductor WorkflowDef
    (AI_MODEL task with server-side LLM orchestration)
```

### Serialization Paths

| Path | When | Conductor Pattern |
|------|------|-------------------|
| **Full extraction (with tools)** | `create_agent(llm, tools=[...])` | AI_MODEL agentic loop + SIMPLE per tool |
| **Full extraction (no tools)** | `create_agent(llm, tools=[])` | AI_MODEL single LLM call |
| **Passthrough** | Legacy `AgentExecutor` (if model/tools undetectable) | Single SIMPLE task running executor locally |

All 25 LangChain examples use full extraction with server-side LLM orchestration.

---

## Feature Support

### System Prompts

System prompts passed via `create_agent(llm, system_prompt="...")` are extracted from the `model_node` closure and sent as `instructions` in the raw_config. The server includes them as the system message in the LLM call.

```python
graph = create_agent(
    llm,
    tools=[my_tool],
    system_prompt="You are an expert data analyst.",
    name="analyst",
)
```

**Extraction mechanism:** `_extract_system_prompt_from_graph()` walks graph node closures looking for the `system_message` free variable (a `SystemMessage` object). If found, `.content` is extracted as a string.

### Tools

LangChain `@tool` decorated functions and `StructuredTool` objects are extracted and registered as individual Conductor workers. The server orchestrates tool calling through the AI_MODEL agentic loop.

```python
@tool
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

graph = create_agent(llm, tools=[search])
```

Each tool's name, description, and JSON schema (from type hints or Pydantic `args_schema`) are included in the raw_config.

### Structured Output

`with_structured_output()` works when used inside `@tool` functions. The structured LLM call happens locally within the tool worker, while the outer agent loop is orchestrated server-side.

```python
extractor = llm.with_structured_output(PersonList)

@tool
def extract_people(text: str) -> str:
    result = extractor.invoke(f"Extract people from: {text}")
    return str(result)

graph = create_agent(llm, tools=[extract_people])
```

### Prompt Templates

`ChatPromptTemplate` and `PromptTemplate` work by formatting the system prompt before passing it to `create_agent`:

```python
filled_system = template.format(persona="Dr. Data", domain="engineering")
graph = create_agent(llm, tools=[...], system_prompt=filled_system)
```

The formatted string is extracted and sent server-side as `instructions`.

### Multi-Turn Conversation

Multi-turn works through AgentSpan's session management. Each `runtime.run()` call is independent — conversation history is managed by the example code, not by a checkpointer.

---

## Validation Coverage

25 of 25 LangChain examples pass through the AgentSpan pipeline:

| # | Example | Features | System Prompt |
|---|---------|----------|---------------|
| 01 | hello_world | No tools, pure LLM | — |
| 02 | react_with_tools | ReAct pattern, tool calling | — |
| 03 | custom_tools | Custom `@tool` functions | — |
| 04 | structured_output | `with_structured_output()` inside tools | — |
| 05 | prompt_templates | `ChatPromptTemplate`, `PromptTemplate` | Yes |
| 06 | chat_history | Multi-turn conversation | — |
| 07 | memory_agent | Session-based memory tools | — |
| 08 | multi_tool_agent | Multiple domain tools | — |
| 09 | math_calculator | Math tools | — |
| 10 | web_search_agent | Web search tools | — |
| 11 | code_review_agent | AST-based code analysis tools | Yes |
| 12 | document_summarizer | Summarization tools | Yes |
| 13 | customer_service_agent | Support tools | Yes |
| 14 | research_assistant | Citation lookup tools | Yes |
| 15 | data_analyst | Data aggregation tools | Yes |
| 16 | content_writer | Multi-format content tools | Yes |
| 17 | sql_agent | NL→SQL with in-memory SQLite, multi-tool chain | Yes |
| 18 | email_drafter | Email drafting tools | Yes |
| 19 | fact_checker | Claim verification tools | Yes |
| 20 | translation_agent | Translation QA tools | Yes |
| 21 | sentiment_analysis | Aspect-based sentiment tools | Yes |
| 22 | classification_agent | Ticket classification tools | Yes |
| 23 | recommendation_agent | Preference-aware tools | Yes |
| 24 | output_parsers | Output parsing tools | Yes |
| 25 | advanced_orchestration | Complex pipeline tools | Yes |

---

## Relationship to LangGraph Integration

Since `create_agent` returns a `CompiledStateGraph`, LangChain agents are a subset of the LangGraph integration. All LangGraph features apply:

- **Server-side LLM orchestration** via AI_MODEL tasks
- **Tool extraction** from ToolNode patterns
- **System prompt extraction** from `model_node` closures
- **Provider inference** from LLM class names (ChatOpenAI → `openai`, ChatAnthropic → `anthropic`, etc.)

See [langgraph-integration.md](langgraph-integration.md) for the complete technical reference including data flow, Conductor construct mapping, and limitations.

## Legacy AgentExecutor Support

The `langchain.py` serializer handles legacy `AgentExecutor` objects with two paths:

1. **Full extraction** — If model and tools are extractable from the executor (via `executor.agent.llm` and `executor.tools`), delegates to the shared `_serialize_full_extraction()` function
2. **Passthrough** — Fallback: the entire executor runs inside a single SIMPLE worker with an `AgentspanCallbackHandler` that streams `tool_call`/`tool_result` events via HTTP POST

The `LangChainNormalizer` on the server side produces a passthrough `AgentConfig` with `_framework_passthrough: true`.

**Note:** `AgentExecutor` is no longer importable from current LangChain versions (v1.2+). All modern LangChain code should use `create_agent` instead.

---

## Limitations

### Inherited from LangGraph

All limitations listed in [langgraph-integration.md § Limitations](langgraph-integration.md#limitations-and-unsupported-features) apply, including:
- Custom reducers (only `operator.add` mapped)
- `Command` construct (not implemented)
- Functional API (`@entrypoint`, `@task`)
- Time travel / replay
- Cross-thread persistence

### LangChain-Specific

| Feature | Status | Notes |
|---------|--------|-------|
| `AgentExecutor` | Deprecated | No longer importable in current LangChain. Use `create_agent`. |
| LCEL chains (non-agent) | Not supported | Only `CompiledStateGraph` objects are detected. Plain LCEL chains (`prompt | llm | parser`) must be wrapped in a `@tool` or used inside `create_agent`. |
| `ConversationBufferMemory` | Not applicable | Legacy memory classes don't apply to `create_agent`. Use tool-based memory patterns. |
| LangServe | Not applicable | AgentSpan replaces LangServe for deployment. |
| LangSmith tracing | Compatible | LangSmith callbacks work inside tool workers alongside `AgentspanCallbackHandler`. |
