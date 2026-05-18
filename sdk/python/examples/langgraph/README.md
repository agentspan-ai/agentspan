# LangGraph Examples

46 examples demonstrating LangGraph integration with Agentspan, from hello-world to advanced multi-agent systems.

## Prerequisites

```bash
uv pip install langgraph langchain-core langchain-openai agentspan
```

| Package | Required | Notes |
|---------|----------|-------|
| `langgraph` | Yes | `StateGraph`, `create_react_agent`, `ToolNode`, `tools_condition` |
| `langchain-core` | Yes | Messages, tools, documents |
| `langchain-openai` | Yes | `ChatOpenAI` LLM provider |
| `langchain-anthropic` | Optional | Only for `43_react_agent_multi_model.py` (requires `ANTHROPIC_API_KEY`) |
| `pydantic` | Some examples | Used for structured output (08) |

## Quick Start

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export OPENAI_API_KEY=sk-...

cd sdk/python
uv run python examples/langgraph/01_hello_world.py
```

## Examples

### Basics (01–05)

| # | File | Topic |
|---|------|-------|
| 01 | `01_hello_world.py` | Simplest agent with `create_agent`, no tools |
| 02 | `02_react_with_tools.py` | ReAct agent with `@tool` functions |
| 03 | `03_memory.py` | Multi-turn memory with `MemorySaver` + `session_id` |
| 04 | `04_simple_stategraph.py` | Custom `StateGraph` with typed state |
| 05 | `05_tool_node.py` | `ToolNode` + `tools_condition` standard loop |

### Graph Patterns (06–10)

| # | File | Topic |
|---|------|-------|
| 06 | `06_conditional_routing.py` | Conditional edges with routing functions |
| 07 | `07_system_prompt.py` | Custom system prompt via `prompt` parameter |
| 08 | `08_structured_output.py` | Structured/JSON output with `with_structured_output` |
| 09 | `09_math_agent.py` | Math tools (calculator, statistics) |
| 10 | `10_research_agent.py` | Multi-step research pipeline |

### Domain Agents (11–15)

| # | File | Topic |
|---|------|-------|
| 11 | `11_customer_support.py` | Customer service triage and response |
| 12 | `12_code_agent.py` | Code generation and explanation |
| 13 | `13_multi_turn.py` | Multi-turn conversation with history |
| 14 | `14_qa_agent.py` | Question answering with context |
| 15 | `15_data_pipeline.py` | Sequential data processing pipeline |

### Advanced Patterns (16–20)

| # | File | Topic |
|---|------|-------|
| 16 | `16_parallel_branches.py` | Parallel execution with `Send` API |
| 17 | `17_error_recovery.py` | Error handling and fallback nodes |
| 18 | `18_tools_condition.py` | Complex tool routing with multiple conditions |
| 19 | `19_document_analysis.py` | Multi-step document analysis |
| 20 | `20_planner_agent.py` | Plan → Execute → Review pipeline |

### Composition & Reliability (21–25)

| # | File | Topic |
|---|------|-------|
| 21 | `21_subgraph.py` | Nested subgraphs for modular composition |
| 22 | `22_human_in_the_loop.py` | Interrupt/resume with human approval |
| 23 | `23_retry_on_error.py` | Automatic retry with `RetryPolicy` |
| 24 | `24_map_reduce.py` | Fan-out / fan-in with `Send` API |
| 25 | `25_supervisor.py` | Supervisor orchestrating specialist agents |

### Multi-Agent & Memory (26–30)

| # | File | Topic |
|---|------|-------|
| 26 | `26_agent_handoff.py` | Explicit agent handoff (triage → specialist) |
| 27 | `27_persistent_memory.py` | Cross-session state with `MemorySaver` |
| 28 | `28_streaming_tokens.py` | Token-by-token streaming with `stream_mode="messages"` |
| 29 | `29_tool_categories.py` | Organized tool categories (math, string, date) |
| 30 | `30_code_interpreter.py` | Safe expression evaluation and code analysis |

### Intelligence Patterns (31–35)

| # | File | Topic |
|---|------|-------|
| 31 | `31_classify_and_route.py` | LLM-based classification + domain routing |
| 32 | `32_reflection_agent.py` | Generate → critique → improve loop |
| 33 | `33_output_validator.py` | Generate → validate → retry until schema passes |
| 34 | `34_rag_pipeline.py` | RAG with retrieve → grade → rewrite → generate |
| 35 | `35_conversation_manager.py` | Sliding window + auto-summarization |

### Advanced Multi-Agent (36–40)

| # | File | Topic |
|---|------|-------|
| 36 | `36_debate_agents.py` | Two agents arguing opposing positions |
| 37 | `37_document_grader.py` | Score + filter documents for relevance |
| 38 | `38_state_machine.py` | Order processing as an explicit state machine |
| 39 | `39_tool_call_chain.py` | Chaining sequential tool calls (ToolNode loop) |
| 40 | `40_agent_as_tool.py` | Compiled graph wrapped as `@tool` for orchestrators |

### ReAct Variants & Production (41–46)

| # | File | Topic |
|---|------|-------|
| 41 | `41_react_agent_basic.py` | Basic ReAct pattern |
| 42 | `42_react_agent_system_prompt.py` | ReAct with system prompt |
| 43 | `43_react_agent_multi_model.py` | Multi-model ReAct (OpenAI + Anthropic) |
| 44 | `44_context_condensation.py` | Orchestrator + sub-agent stress test |
| 45 | `45_advanced_orchestration.py` | Complex orchestration patterns |
| 46 | `46_crash_and_resume.py` | Crash recovery: resume execution after process restart |

## Common Patterns

### Basic `create_agent` (detected as `langgraph`)
```python
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

@tool
def my_tool(input: str) -> str:
    """Tool description."""
    return f"Result: {input}"

graph = create_agent(llm, tools=[my_tool], name="my_agent")

with AgentRuntime() as runtime:
    result = runtime.run(graph, "your prompt")
    result.print_result()
```

### Custom `StateGraph`
```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class State(TypedDict):
    messages: list
    result: str

def my_node(state: State) -> State:
    return {"result": "done"}

builder = StateGraph(State)
builder.add_node("process", my_node)
builder.add_edge(START, "process")
builder.add_edge("process", END)
graph = builder.compile(name="my_graph")
```

### Session-based memory
```python
with AgentRuntime() as runtime:
    result = runtime.run(graph, "prompt", session_id="user-123")
```

### Crash & Resume
```python
# Deploy once (CI/CD):
with AgentRuntime() as runtime:
    runtime.deploy(graph)

# Long-running worker process (restart on crash):
with AgentRuntime() as runtime:
    runtime.serve(graph)  # blocks, polls for tasks

# After a crash, just restart serve() — workers reconnect,
# stalled tasks resume automatically. No special logic needed.
```

## Requirements

- Python 3.11+
- `uv` package manager
- `AGENTSPAN_SERVER_URL` — Agentspan server endpoint
- `OPENAI_API_KEY` — OpenAI API key for `ChatOpenAI`
