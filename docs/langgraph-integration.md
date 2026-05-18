# LangGraph → AgentSpan Integration

How LangGraph graphs are translated and executed through the AgentSpan platform.

## Overview

AgentSpan compiles LangGraph `StateGraph` and `create_react_agent` graphs into Conductor workflow definitions. The process has three phases:

1. **Serialization** (Python SDK) — Introspects the LangGraph graph object, extracts nodes/edges/tools, and produces a `raw_config` dict + worker functions
2. **Normalization** (Server) — Converts the `raw_config` into a canonical `AgentConfig` with tools and metadata
3. **Compilation** (Server) — Transforms the `AgentConfig` into a Conductor `WorkflowDef` with typed tasks

The system supports three serialization paths, chosen automatically based on the graph structure:

| Path | When | Conductor Pattern |
|------|------|-------------------|
| **Full extraction** | `create_agent`/`create_react_agent` (with or without tools) | AI_MODEL + SIMPLE per tool |
| **Graph-structure** | Custom `StateGraph` with detectable model | Node/edge workflow with typed tasks |
| **Passthrough** | Fallback (no model found, multi-arg nodes) | Single SIMPLE task running graph locally |

---

## Serialization Paths

### Path 1: Full Extraction

**Trigger:** Model found in graph — either with tools (ToolNode) or without (pure LLM call). This covers both `create_react_agent` with tools and `create_agent` with no tools.

Used by `create_agent`/`create_react_agent` graphs (examples: 01, 02, 03, 05, 07, 08, 09, 10, 12, 13, 18, 29, 30, 41, 42).

The serializer:
1. Finds the LLM object via `_find_model_in_graph()` — walks `graph.nodes` looking for objects with `model_name` / `model` attributes
2. Infers the provider from the class name (ChatOpenAI → `openai`, ChatAnthropic → `anthropic`, etc.)
3. Finds tools via `_find_tools_in_graph()` — searches nodes for `tools_by_name` dict (ToolNode pattern)
4. For each tool, extracts name, description, JSON schema, and callable
5. Extracts system prompt via `_extract_system_prompt_from_graph()` — walks node closures looking for `system_message` (set by `create_agent`'s `system_prompt` parameter)
6. Registers one worker per tool (may be zero for pure LLM agents)

**Output format:**
```python
raw_config = {
    "name": "my_agent",
    "model": "openai/gpt-4o-mini",
    "instructions": "You are a helpful pirate.",  # from system_prompt param, if present
    "tools": [
        {"_worker_ref": "search", "description": "Search the web", "parameters": {...}},
    ]
}
```

**Conductor result:** The server compiles this as an AI_MODEL task (agentic loop with tool calling) — identical to OpenAI agents. For agents with no tools, the AI_MODEL task runs a single LLM call with the system prompt and user message.

### Path 2: Graph-Structure

**Trigger:** Model found BUT no ToolNode tools (custom StateGraph with explicit nodes/edges).

Used by most custom LangGraph workflows (examples: 04, 06, 11, 15, 16, 17, 19, 20, 23, 24, 25, 26, 27, 31–38, 40).

The serializer introspects the compiled graph to extract:
- **Nodes**: function references from `graph.nodes` dict
- **Edges**: simple `(source, target)` from `graph.builder.edges`
- **Conditional edges**: `(source, router_func, target_map, is_dynamic)` from `graph.builder.branches`
- **State reducers**: from `graph.channels` (e.g., `Annotated[list, operator.add]`)
- **Retry policies**: per-node metadata from `graph.builder._nodes`
- **Recursion limit**: from `graph.config` or default 25

Each node is classified as:
- **Regular node** — plain function, becomes a SIMPLE worker
- **LLM node** — function uses a detected LLM variable, split into prep + finish workers
- **Human node** — decorated with `@human_task`, becomes a Conductor HUMAN task

**Output format:**
```python
raw_config = {
    "name": "my_workflow",
    "model": "openai/gpt-4o-mini",
    "_graph": {
        "nodes": [
            {"name": "fetch", "_worker_ref": "my_workflow_fetch"},
            {"name": "analyze", "_llm_node": True,
             "_llm_prep_ref": "my_workflow_analyze_prep",
             "_llm_finish_ref": "my_workflow_analyze_finish"},
            {"name": "review", "_human_node": True, "_human_prompt": "Review the analysis"},
        ],
        "edges": [{"source": "fetch", "target": "analyze"}],
        "conditional_edges": [
            {"source": "review", "_router_ref": "my_workflow_review_router",
             "targets": {"approve": "__end__", "revise": "analyze"}}
        ],
        "_reducers": {"results": "add"},
        "_retry_policies": {"fetch": {"max_attempts": 3}},
        "_recursion_limit": 25
    }
}
```

### Path 3: Passthrough

**Trigger:** No model detected in the graph. This is the fallback for graphs where the LLM object cannot be found via introspection.

Used by: examples 21, 28.

The entire graph runs inside a single SIMPLE worker process. The worker calls `graph.stream(...)` locally, forwarding thinking/tool_call/tool_result events as SSE.

**Output format:**
```python
raw_config = {
    "name": "my_agent",
    "_worker_name": "my_agent"
}
```

---

## Feature-by-Feature Translation

### 1. Sequential Nodes

**LangGraph:**
```python
graph.add_edge("node_a", "node_b")
graph.add_edge("node_b", "node_c")
```

**Conductor:** Sequential SIMPLE tasks, each receiving state from the previous task's output.

```
node_a (SIMPLE) → node_b (SIMPLE) → node_c (SIMPLE)
```

State is threaded via Conductor expressions: `${node_a.output.state}` → node_b's input.

### 2. LLM Nodes (Server-Side LLM Calls)

**LangGraph:**
```python
def analyze(state):
    response = llm.invoke([SystemMessage(...), HumanMessage(state["text"])])
    return {"analysis": response.content}
```

**Conductor:** Three-task pipeline with a conditional bypass.

```
prep (SIMPLE)
  → SWITCH(_skip_llm)
      case "true":  INLINE passthrough (pre-computed result)
      default:      LLM_CHAT_COMPLETE → finish (SIMPLE)
  → coalesce (INLINE)
```

**How it works:**

1. **Prep worker** replaces the module-level `llm` variable with a `_LLMCaptureProxy`. When the function calls `llm.invoke(messages)`, the proxy raises `_CapturedLLMCall` — intercepting the messages without making an API call. The prep worker serializes these messages and returns them.

2. **LLM_CHAT_COMPLETE** is a native Conductor system task that calls the LLM provider server-side with the captured messages. This gives the server control over model selection, rate limiting, and cost tracking.

3. **Finish worker** replaces `llm` with a `_LLMMockProxy` that returns the server's LLM response. The function runs to completion, producing the state update as if the LLM call happened normally.

4. **Conditional bypass (SWITCH):** If the function completes *without* calling `llm.invoke()` (e.g., early return when no relevant documents), the prep worker sets `_skip_llm: true` and returns the pre-computed result. The SWITCH skips the LLM task entirely.

Thread safety: all LLM variable swaps are protected by `_llm_intercept_lock`.

### 3. Conditional Routing

**LangGraph:**
```python
def route(state):
    if state["sentiment"] == "positive":
        return "celebrate"
    return "console"

graph.add_conditional_edges("analyze", route, {"celebrate": "celebrate", "console": "console"})
```

**Conductor:** Router SIMPLE task → SWITCH → branch tasks.

```
router (SIMPLE) → returns {decision: "celebrate", state: {...}}
  ↓
SWITCH (value-param evaluator on decision)
  case "celebrate": celebrate_tasks...
  case "console":   console_tasks...
  ↓
coalesce (INLINE) — unifies branch outputs
```

The router worker calls the original routing function and returns the decision string. The SWITCH task dispatches to the matching branch.

### 4. Parallel Branches (FORK_JOIN)

**LangGraph:**
```python
graph.add_edge(START, "pros")
graph.add_edge(START, "cons")
graph.add_edge("pros", "merge")
graph.add_edge("cons", "merge")
```

**Conductor:**
```
FORK_JOIN
  ├─ branch 0: pros_tasks...
  └─ branch 1: cons_tasks...
JOIN (waits for both)
  ↓
INLINE merge (reducer-aware state combination)
```

**State merge logic** (JavaScript in INLINE task):
- Fields with `Annotated[list, operator.add]` reducer: arrays are concatenated across branches
- All other fields: last-write-wins (last branch value overwrites)

### 5. Dynamic Fan-Out (Send API / FORK_JOIN_DYNAMIC)

**LangGraph:**
```python
from langgraph.types import Send

def fan_out(state):
    return [Send("summarize", {"document": doc}) for doc in state["documents"]]

graph.add_conditional_edges("generate", fan_out, ["summarize"])
```

**Conductor:**
```
router (SIMPLE)
  → returns {dynamic_tasks: [{node: "summarize", input: {document: "..."}}, ...]}
  ↓
INLINE enrich
  → converts to Conductor FORK_JOIN_DYNAMIC format:
    {dynamicTasks: [{name, taskReferenceName, type, inputParameters}, ...]}
  ↓
FORK_JOIN_DYNAMIC (creates N parallel SIMPLE tasks at runtime)
  ↓
JOIN
  ↓
INLINE merge (reducer-aware, iterates over join output keys)
```

**Detection:** The serializer inspects the routing function's bytecode (`co_names`) for references to `Send`. The router worker checks if the return value is a list of objects with `.node` and `.arg` attributes.

The enrich INLINE maps each `node` name to its registered worker ref and builds the Conductor task format. The merge INLINE handles an unknown number of branches (determined at runtime) by iterating over all keys in the JOIN output.

### 6. Cycles and Loops (DO_WHILE)

**LangGraph:**
```python
def should_continue(state):
    if state["iterations"] < 3:
        return "refine"   # back-edge → cycle
    return "__end__"      # exit

graph.add_conditional_edges("refine", should_continue, {"refine": "refine", "__end__": END})
```

**Conductor:**
```
DO_WHILE
  condition: iteration < recursion_limit AND decision in back_edges
  body:
    state_bridge (INLINE) — first iteration uses pre-loop state, subsequent use router output
    ...loop body tasks...
    router (SIMPLE) — evaluates continue/exit condition
```

**Cycle detection:** During topological traversal, if a conditional edge target has already been visited, it's classified as a back-edge (cycle). The compiler extracts all tasks between the cycle start and the current router as the loop body.

**State bridge:** Handles the first-vs-subsequent-iteration difference. On iteration 1, the first task in the loop body needs state from *before* the loop. On iteration 2+, it needs state from the router's output (end of previous iteration). The bridge INLINE selects the correct source.

**Recursion limit:** Mapped from LangGraph's `recursion_limit` config (default 25) to the DO_WHILE's iteration cap.

### 7. Human-in-the-Loop

**LangGraph:**
```python
from agentspan.agents.frameworks.langgraph import human_task

@human_task(prompt="Review the draft and provide verdict + feedback.")
def review(state):
    pass
```

**Conductor:** Compiled as a HUMAN system task pipeline:
```
HUMAN task (pauses execution, waits for external input via API/UI)
  ↓
validation (INLINE) — validates human response format
  ↓
normalization (INLINE) — normalizes response
  ↓
process (SIMPLE) — merges human input into state
```

The `@human_task` decorator marks the function with `_agentspan_human_task = True`. No worker is registered for human nodes — the Conductor HUMAN task type handles external input natively. The server auto-generates the response form schema from the workflow context and the prompt string.

### 8. State Reducers

**LangGraph:**
```python
class State(TypedDict):
    results: Annotated[list, operator.add]  # concatenate across branches
    topic: str                               # last-write-wins
```

**Extraction:** The serializer inspects `graph.channels` for `BinaryOperatorAggregate` types and extracts `operator.add` → `"add"` reducer mapping.

**Conductor:** Applied in every FORK_JOIN/FORK_JOIN_DYNAMIC merge INLINE task:

```javascript
// Generated merge JavaScript (simplified):
for (var k in branch_state) {
    if (k === 'results') {
        // "add" reducer: concatenate arrays
        merged[k] = (merged[k] || []).concat(branch_state[k]);
    } else {
        // default: last-write-wins
        merged[k] = branch_state[k];
    }
}
```

### 9. Retry Policies

**LangGraph:**
```python
graph.add_node("fetch", fetch_data, retry=RetryPolicy(max_attempts=3, initial_interval=1.0))
```

**Conductor:** Mapped to Conductor task-level retry settings:
- `max_attempts` → `retryCount` (minus 1, since Conductor counts retries not attempts)
- `initial_interval` → `retryDelaySeconds`
- `backoff_factor` → `backoffScaleFactor`
- `max_interval` → capped via backoff calculation

### 10. Agent-as-Tool (SUB_WORKFLOW)

**LangGraph:**
```python
from agentspan.agents.tool import AgentTool

research_tool = AgentTool(name="researcher", agent=research_graph, description="Research a topic")
main_graph = create_react_agent(llm, tools=[calculator, research_tool])
```

**Conductor:** The child agent is recursively compiled into its own workflow definition. The parent workflow invokes it as a SUB_WORKFLOW task:

```
parent AI_MODEL loop
  → tool_call: "researcher"
  → SUB_WORKFLOW (child agent's compiled workflow)
  → tool_result fed back to parent
```

The `LangGraphNormalizer` detects `AgentTool` entries (via `_type: "AgentTool"`) and recursively calls `normalize()` on the embedded agent config. The compiler creates an inline workflow definition or references an external one.

### 11. Subgraphs

**LangGraph:**
```python
inner = StateGraph(InnerState)
# ... build inner graph ...
inner_compiled = inner.compile()

def run_inner(state):
    result = inner_compiled.invoke({"text": state["analysis_text"]})
    return {"sentiment": result["sentiment"], ...}

outer = StateGraph(OuterState)
outer.add_node("analysis", run_inner)
```

**AgentSpan:** Compiled as `SUB_WORKFLOW` with the same intercept pattern used for LLM nodes:

1. **Detection:** `_find_subgraph_in_func()` checks node function bytecode references (`co_names`) against globals for `CompiledStateGraph` objects
2. **Serialization:** Subgraph is recursively serialized via `_serialize_graph_structure()` with a unique name prefix (`{parent}_{node}`)
3. **Prep worker:** Runs the node function with `_SubgraphCaptureProxy` which captures the `.invoke()` input (e.g., `{"text": state["analysis_text"]}`)
4. **SUB_WORKFLOW:** Server compiles the subgraph config into a nested `WorkflowDef` and executes it inline. The subgraph workflow receives `state` directly (not a prompt string) via `${workflow.input.state}` and returns both `state` and `result` in output
5. **Finish worker:** Runs the node function with `_SubgraphMockProxy` (returns the SUB_WORKFLOW's output state), producing the parent state update
6. **SWITCH for skip:** Like LLM nodes, a SWITCH task handles the edge case where the function completes without calling `subgraph.invoke()`

**Conductor pipeline:**
```
prep SIMPLE → SWITCH(_skip_subgraph) → [passthrough INLINE | SUB_WORKFLOW → finish SIMPLE] → coalesce INLINE
```

**Subgraph workflow differences from regular graph-structure workflows:**
- Input: `${workflow.input.state}` (full state dict) instead of `{inputKey: ${workflow.input.prompt}}`
- Output: includes `state` alongside `result` for the parent finish worker
- Marked with `_is_subgraph: true` in the `_graph` metadata

**Example:** `21_subgraph.py` — parent graph (prepare → analysis → build_report) with analysis node invoking a 3-node LLM subgraph (sentiment → keywords → summarize). All 3 subgraph LLM calls execute as server-side `LLM_CHAT_COMPLETE` tasks within the SUB_WORKFLOW.

### 12. State Reconstitution

When state passes through Conductor (JSON serialization), type information is lost. The SDK includes `_reconstitute_state()` which runs before every worker function:

- **LangChain Documents:** Dicts with `page_content` key are reconstructed as `Document(page_content=..., metadata=...)` objects
- **Stringified dicts:** If the state has a single string field containing a dict literal (e.g., `str(state)` was used as the prompt), it's parsed back via `ast.literal_eval`

---

## Data Flow

```
User Code                    Python SDK                     Server
─────────                    ──────────                     ──────

StateGraph / create_agent    serialize_langgraph()
  │                            │
  │                            ├─ Introspect graph
  │                            ├─ Extract nodes/edges
  │                            ├─ Build worker functions
  │                            ├─ Produce raw_config
  │                            │
  │                          AgentRuntime.run()
  │                            │
  │                            ├─ POST /agent/start
  │                            │   (raw_config + framework)
  │                            │                ────────────► LangGraphNormalizer.normalize()
  │                            │                               │
  │                            │                               ├─ Detect path (full/graph/passthrough)
  │                            │                               ├─ Build AgentConfig
  │                            │                               │
  │                            │                             AgentCompiler.compile()
  │                            │                               │
  │                            │                               ├─ Build Conductor WorkflowDef
  │                            │                               ├─ Register workflow
  │                            │                               ├─ Start execution
  │                            │                               │
  │                            ├─ Register workers           ◄─ Conductor polls workers
  │                            │   (TaskHandler)               │
  │                            │                               │
  │                            ├─ Workers execute:             │
  │                            │   node_func(state)            │
  │                            │   router_func(state)          │
  │                            │   llm_prep/finish(state)      │
  │                            │                               │
  │                            ├─ Poll for completion          │
  │                            │                               │
  ◄────────────────────────────┤ Return result                 │
```

---

## Validation Coverage

41 of 41 LangGraph examples pass through the AgentSpan pipeline:

| # | Example | Path | Features Exercised |
|---|---------|------|--------------------|
| 01 | hello_world | full extraction | create_agent, no tools, server-side LLM |
| 02 | react_with_tools | full extraction | create_react_agent, tool calling |
| 03 | memory | full extraction | create_agent, conversation history, server-side LLM |
| 04 | simple_stategraph | graph-structure | sequential nodes, LLM intercept, conditional routing |
| 05 | tool_node | full extraction | ToolNode, tool schemas |
| 06 | conditional_routing | graph-structure | conditional edges, SWITCH |
| 07 | system_prompt | full extraction | create_agent, system prompt extracted from closure |
| 08 | structured_output | full extraction | create_agent, structured output, server-side LLM |
| 09 | math_agent | full extraction | tool calling, calculator |
| 10 | research_agent | full extraction | multi-tool agent |
| 11 | customer_support | graph-structure | conditional routing, LLM nodes |
| 12 | code_agent | full extraction | code execution tool |
| 13 | multi_turn | full extraction | multi-turn conversation, server-side LLM |
| 14 | qa_agent | graph-structure | simple Q&A pipeline |
| 15 | data_pipeline | graph-structure | multi-step data processing |
| 16 | parallel_branches | graph-structure | FORK_JOIN, state reducers (`operator.add`) |
| 17 | error_recovery | graph-structure | error handling, conditional retry |
| 18 | tools_condition | full extraction | tools_condition helper |
| 19 | document_analysis | graph-structure | multi-node document pipeline |
| 20 | planner_agent | graph-structure | plan → execute → evaluate loop |
| 21 | subgraph | graph-structure | SUB_WORKFLOW, recursive compilation, subgraph intercept |
| 22 | human_in_the_loop | graph-structure | `@human_task`, HUMAN system task, conditional routing |
| 23 | retry_on_error | graph-structure | retry policies, DO_WHILE |
| 24 | map_reduce | graph-structure | Send API, FORK_JOIN_DYNAMIC, reducers |
| 25 | supervisor | graph-structure | supervisor pattern, conditional routing |
| 26 | agent_handoff | graph-structure | multi-agent handoff via routing |
| 27 | persistent_memory | graph-structure | state persistence across turns |
| 29 | tool_categories | full extraction | categorized tools |
| 30 | code_interpreter | full extraction | code execution |
| 31 | classify_and_route | graph-structure | classification → conditional routing |
| 32 | reflection_agent | graph-structure | DO_WHILE cycle (reflect → revise) |
| 33 | output_validator | graph-structure | validation loop |
| 34 | rag_pipeline | graph-structure | Document reconstitution, LLM nodes |
| 35 | conversation_manager | graph-structure | multi-turn with state management |
| 36 | debate_agents | graph-structure | multi-agent debate, cycles |
| 37 | document_grader | graph-structure | conditional LLM skip (`_skip_llm`) |
| 38 | state_machine | graph-structure | state string parsing |
| 39 | tool_call_chain | graph-structure | chained tool invocations |
| 40 | agent_as_tool | graph-structure | AgentTool, SUB_WORKFLOW |
| 41 | react_agent_basic | full extraction | basic ReAct pattern |
| 42 | react_agent_system_prompt | full extraction | ReAct with system prompt |
| 44 | context_condensation | full extraction | Stress test: orchestrator + sub-agent @tool (25 domains, ~72s) |

---

## Conductor Construct Mapping

| LangGraph Concept | Conductor Task Type | Notes |
|---|---|---|
| Node function | SIMPLE | Worker polls and executes |
| LLM call in node | Prep (SIMPLE) → LLM_CHAT_COMPLETE → Finish (SIMPLE) | Server-side LLM with conditional bypass |
| `add_edge(a, b)` | Sequential task ordering | State threaded via `${ref.output.state}` |
| `add_conditional_edges` | Router (SIMPLE) → SWITCH | Value-param evaluator |
| Parallel from START | FORK_JOIN → JOIN → INLINE merge | Reducer-aware |
| `Send()` API | FORK_JOIN_DYNAMIC → JOIN → INLINE merge | Runtime-determined parallelism |
| Cycles (back-edges) | DO_WHILE + state bridge | Iteration cap from recursion_limit |
| `@human_task` | HUMAN system task | Pauses for external input |
| `AgentTool` | SUB_WORKFLOW | Recursive agent compilation |
| Subgraph `.invoke()` | Prep (SIMPLE) → SUB_WORKFLOW → Finish (SIMPLE) | Subgraph compiled as nested workflow |
| State reducers | INLINE merge JavaScript | `operator.add` → array concat |
| `RetryPolicy` | Task-level retry settings | max_attempts, backoff, interval |
| `create_agent`/`create_react_agent` | AI_MODEL agentic loop | Server-side LLM, with or without tools. System prompt extracted from closure. |
| Entire graph (fallback) | Single SIMPLE task | Passthrough: graph.stream() locally |

---

## Limitations and Unsupported Features

This section documents what is **not** supported, what falls back to **passthrough** (local execution, bypassing server orchestration), and **known limitations** of supported features. This is the source of truth for LangGraph parity.

### Not Supported

These LangGraph features are **not implemented** and will either error or silently produce incorrect results.

| Feature | LangGraph API | Status | Notes |
|---------|--------------|--------|-------|
| `Command` construct | `Command(goto=..., update=...)` | Not implemented | Dynamic routing with state updates. Planned (Task #42). |
| Custom reducers | `Annotated[list, my_custom_fn]` | Warning logged | Only `operator.add` is mapped. Custom Python callables are detected and a warning is logged at serialization time. These fields will use last-write-wins in FORK_JOIN merge, which may cause data loss. |
| Functional API | `@entrypoint`, `@task` | Not implemented | LangGraph's functional API is a different programming model entirely. |
| `CachePolicy` | `CachePolicy(ttl=...)` | Not implemented | No equivalent in Conductor task model. |
| Managed values | `RemainingSteps`, `IsLastStep` | Not implemented | These depend on LangGraph's internal recursion tracking. |
| Private state channels | `PrivateAttr`, channel-level access control | Not implemented | Conductor state is a flat JSON dict. |
| `InputState` / `OutputState` distinction | Separate TypedDict for input vs output | Not implemented | AgentSpan treats graph state as a single schema. Input validation and output filtering are not enforced. |
| Time travel / replay | `get_state_history()`, replay from checkpoint | Not implemented | No checkpoint storage. |
| Cross-thread persistence | `BaseStore`, `InMemoryStore` | Not implemented | No cross-execution memory store. |
| `InjectedState` / `InjectedStore` | Tool parameter injection | Not implemented | Tools receive explicit inputs only. |
| `ValidationNode` | Built-in validation node type | Not implemented | Use regular nodes with validation logic. |
| Middleware | Request/response middleware hooks | Not implemented | No equivalent in Conductor. |
| Deferred nodes | `defer=True` | Not implemented | All nodes execute eagerly. |
| LangGraph Platform features | Cron jobs, double texting, assistants API | Not applicable | These are LangGraph Cloud features, not graph features. |
| CompiledStateGraph as tool parameter | Passing a graph object directly as a tool | Not supported | LangChain's `ToolNode` rejects non-callable tools. Wrap in a `@tool` function that calls `.invoke()`. |
| Server-side token streaming | Real-time token streaming from LLM nodes | Not supported | `LLM_CHAT_COMPLETE` returns the full response. No incremental token forwarding. |

### Passthrough Only (Local Execution)

These features "work" in the sense that the graph runs, but the entire graph executes inside a single SIMPLE worker process. The server has no visibility into individual nodes, cannot control LLM calls, and cannot orchestrate steps independently. This defeats the purpose of server-side orchestration.

| Feature | Why Passthrough | What Triggers It |
|---------|----------------|------------------|
| Graphs where no model can be detected | Serializer can't find LLM object via introspection | No object with `model_name`/`model` attribute in graph nodes or globals |
| Nodes with >1 positional arg in custom StateGraphs | Cannot run as standalone SIMPLE workers | Function signature has `(state, config)` or similar |

**Previously passthrough, now server-side:** `create_agent` graphs (with or without tools/system prompt) are now detected as full extraction. The serializer extracts the model from the graph nodes and the system prompt from `model_node`'s closure (`system_message` free variable). Examples 01, 03, 07, 08, 13 all use server-side LLM orchestration.

### Known Limitations of Supported Features

These features ARE supported and orchestrated server-side, but have known edge cases or limitations.

#### Bytecode inspection for detection (LLM, subgraph, Send API)

Detection relies on CPython bytecode inspection (`func.__code__.co_names` + `func.__globals__`). This breaks with:
- **Aliased imports**: `from langchain_openai import ChatOpenAI as MyLLM` — the global variable name won't match the detection pattern
- **Closures / nested functions**: Variables captured in closures don't appear in `co_names`
- **Decorators that wrap functions**: If a decorator replaces `__code__`, the original names are lost
- **Non-CPython runtimes**: PyPy, GraalPy don't guarantee the same `co_names` layout

**Mitigation**: Use straightforward module-level LLM/subgraph variable assignments. Avoid aliasing or wrapping.

#### Global variable mutation for LLM/subgraph interception

Prep and finish workers swap module-level globals (`func.__globals__[var_name]`) with proxy objects under a process-wide lock (`_llm_intercept_lock`). This means:
- **One node function at a time** per process — concurrent interceptions are serialized
- **Same global namespace** — if two node functions reference the same LLM variable, they share the lock
- **Error recovery** — if the function raises, the `finally` block restores the original, but there's a window during which another thread could see the proxy

This is safe for the current single-threaded Conductor worker model but would need redesign for concurrent execution.

#### State reducers

Only `operator.add` is mapped to array concatenation in FORK_JOIN/FORK_JOIN_DYNAMIC merge. All other fields use last-write-wins. Custom reducer functions (arbitrary Python callables) are detected and a **warning is logged** at serialization time, but the server has no way to execute arbitrary Python in its JavaScript INLINE tasks.

#### Retry policies

`max_attempts`, `initial_interval`, and `backoff_factor` are mapped to Conductor task retry settings. The following LangGraph retry params are **not mapped** and will log a warning:
- `max_interval` — Conductor has no direct equivalent (backoff is unbounded)
- `jitter` — Conductor doesn't support jitter in retry delays

#### Multiple conditional edges from the same source node

If a graph has two `add_conditional_edges()` calls from the same source node, the targets are merged but the **last router function wins**. This is because Conductor's SWITCH can only evaluate one routing decision per node. A warning is logged when this occurs.

#### Result extraction heuristic

The compiled workflow extracts the "result" from the final node's state using hardcoded field names: `result`, `final_report`, `output` (checked in that order). If your graph's output uses a different field name, the workflow output will be empty. The full state is always available via the state output.

#### INLINE JavaScript in Conductor tasks

Merge, bridge, coalesce, and enrich logic runs as GraalJS inside Conductor INLINE tasks. These are string-concatenated in Java with no compile-time validation. While they are covered by integration tests, there are no unit tests for the generated JavaScript itself.
