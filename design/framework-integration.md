# Framework Integration

**Status:** Consolidated 2026-06-26

**Scope.** This is the single canonical reference for running agents authored in third-party frameworks on the AgentSpan platform. Framework graphs and agents become Conductor tasks: depending on what the SDK can introspect, a framework agent either decomposes into native server-side tasks (model + tool tasks, nodes/edges) or runs **passthrough** — the whole graph/agent executes inside one durable Conductor SIMPLE worker while pushing thinking/tool-call/tool-result events to the server non-blocking. Either way the user keeps their framework's authoring API and the call is always the same: `runtime.run(frameworkAgentOrGraph, prompt)`. This doc covers the passthrough execution model, the serialization reference for each framework (LangGraph being the definitive one), and the OCG retrieval integration.

**Siblings.** Platform model: [agentspan-design.md](agentspan-design.md). SDK surface: [sdk-design.md](sdk-design.md). HTTP API: [api-design.md](api-design.md). Credential resolution and tool dispatch: [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md). Per-SDK usage docs: [Python framework-agents.md](../sdk/python/docs/framework-agents.md), [TypeScript framework-agents.md](../sdk/typescript/docs/framework-agents.md).

---

## 1. Scope and the passthrough execution model

A framework agent reaches the server as a `raw_config` dict plus a set of worker closures. The server normalizes the `raw_config` into a canonical `AgentConfig` and compiles it into a Conductor `WorkflowDef`. Two broad outcomes:

- **Decomposed** — the SDK introspects the agent and the server compiles native tasks: an AI_MODEL agentic loop with one SIMPLE task per tool, or a node/edge workflow of typed tasks. The server controls model selection, tool dispatch, retries, and step-level orchestration.
- **Passthrough** — the SDK cannot (or should not) decompose the agent, so the entire framework runtime runs inside one SIMPLE worker. The server sees a single durable task; the worker forwards events so observability and durability still apply, but step-level orchestration does not.

The detection rule is per-framework (see each section), but the shared property is: **detection is duck-typed in the SDK, no framework is imported by AgentSpan, and framework packages are optional peer dependencies.** Whichever path is chosen, events are pushed non-blocking from the worker to the server so the calling code never waits on instrumentation.

| Framework | Primary path | Falls back to |
|---|---|---|
| OpenAI Agents SDK | Full extraction (AI_MODEL + tools) | — |
| LangGraph | Full extraction / graph-structure | Passthrough |
| LangChain (`create_agent`) | Full extraction via LangGraph | Passthrough (legacy `AgentExecutor`) |
| Google ADK | Full extraction (AI_MODEL + tools / orchestration agents) | — |
| Claude Agent SDK | Passthrough (by design) | — |
| OCG retrieval | HTTP tasks (SDK-baked) | — |

---

## 2. Common passthrough architecture

All passthrough bridges share the same shape, so it is documented once here and referenced from each framework section.

**Single durable task.** The server's `compileFrameworkPassthrough()` produces a `WorkflowDef` with a single SIMPLE task. The normalizer sets `metadata._framework_passthrough = true` and emits one `ToolConfig` with `toolType = "worker"`. The task receives `prompt`, `session_id`, `media`, and `cwd` and hands them to the worker.

**Worker closure, not JSON.** Framework objects often contain callables (hooks, custom tools, compiled graphs) that cannot be JSON-serialized. The SDK therefore keeps the object in a worker closure and sends only a minimal `raw_config = {name, _worker_name}` to the server. `_build_passthrough_func()` builds the worker per framework; `_register_passthrough_worker()` registers it as a Conductor task def (default 600s timeout).

**Callback handlers → SSE events.** Each framework exposes an instrumentation hook (LangChain/LangGraph callback handler, Claude Agent SDK hooks, etc.). AgentSpan attaches its own handler that maps framework events to AgentSpan stream events and pushes them via fire-and-forget HTTP `POST /api/agent/events/{executionId}` using a module-level `ThreadPoolExecutor(max_workers=4)`. User-supplied handlers/hooks are preserved and run first; AgentSpan handlers are additive and defensive (try/except — instrumentation must never crash the agent). Typical event types: `tool_call`, `tool_result`, `tool_error`, `thinking`, `subagent_start`/`subagent_stop`, `notification`, `agent_stop`.

**Credential injection contract.** The passthrough worker resolves execution-level credentials from the `_workflow_credentials` registry by execution token, injects them into `os.environ` before running, and removes them in a `finally` block. This is the same contract every tool worker follows — see [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md) for the full credential resolution model (names never leave the server, placeholders resolved at dispatch). Credentials are declared per-agent (`credentials=[...]`) or per-run.

**Async in a sync worker.** Conductor workers are sync functions in `ThreadPoolExecutor` threads. Async frameworks (Claude Agent SDK, OpenAI streaming) are driven with `asyncio.run(...)`, which creates a fresh event loop — safe because worker threads have no existing loop. Known limitation: this does not work from inside an already-running loop (e.g. Jupyter); workaround is `nest_asyncio` or a separate thread.

---

## 3. LangGraph (definitive serialization reference)

AgentSpan compiles LangGraph `StateGraph` and `create_react_agent`/`create_agent` graphs into Conductor workflow definitions. Three phases:

1. **Serialization** (Python SDK) — introspect the graph, extract nodes/edges/tools, produce a `raw_config` dict + worker functions.
2. **Normalization** (Server) — convert `raw_config` into a canonical `AgentConfig`.
3. **Compilation** (Server) — transform the `AgentConfig` into a Conductor `WorkflowDef` with typed tasks.

The serializer chooses one of three paths automatically based on graph structure:

| Path | When | Conductor Pattern |
|------|------|-------------------|
| **Full extraction** | `create_agent`/`create_react_agent` (with or without tools) | AI_MODEL + SIMPLE per tool |
| **Graph-structure** | Custom `StateGraph` with detectable model | Node/edge workflow with typed tasks |
| **Passthrough** | Fallback (no model found, multi-arg nodes) | Single SIMPLE task running graph locally (see §2) |

### 3.1 Serialization paths

#### Path 1: Full Extraction

**Trigger:** Model found in graph — either with tools (ToolNode) or without (pure LLM call). Covers both `create_react_agent` with tools and `create_agent` with no tools.

The serializer:
1. Finds the LLM object via `_find_model_in_graph()` — walks `graph.nodes` for objects with `model_name` / `model` attributes.
2. Infers the provider from the class name (ChatOpenAI → `openai`, ChatAnthropic → `anthropic`, etc.).
3. Finds tools via `_find_tools_in_graph()` — searches nodes for a `tools_by_name` dict (ToolNode pattern).
4. For each tool, extracts name, description, JSON schema, and callable.
5. Extracts the system prompt via `_extract_system_prompt_from_graph()` — walks node closures for `system_message` (set by `create_agent`'s `system_prompt`).
6. Registers one worker per tool (may be zero for pure LLM agents).

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

**Conductor result:** compiled as an AI_MODEL task (agentic loop with tool calling) — identical to OpenAI agents. With no tools, the AI_MODEL task runs a single LLM call with the system prompt and user message.

#### Path 2: Graph-Structure

**Trigger:** Model found BUT no ToolNode tools (custom StateGraph with explicit nodes/edges).

The serializer introspects the compiled graph to extract:
- **Nodes**: function references from `graph.nodes`.
- **Edges**: `(source, target)` from `graph.builder.edges`.
- **Conditional edges**: `(source, router_func, target_map, is_dynamic)` from `graph.builder.branches`.
- **State reducers**: from `graph.channels` (e.g. `Annotated[list, operator.add]`).
- **Retry policies**: per-node metadata from `graph.builder._nodes`.
- **Recursion limit**: from `graph.config` or default 25.

Each node is classified as: **regular** (plain function → SIMPLE worker), **LLM node** (uses a detected LLM variable → prep + finish workers), or **human** (`@human_task` → Conductor HUMAN task).

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

#### Path 3: Passthrough

**Trigger:** No model detected in the graph (introspection cannot find the LLM object). The entire graph runs inside one SIMPLE worker that calls `graph.stream(...)` locally and forwards thinking/tool_call/tool_result events as SSE (see §2).

```python
raw_config = {"name": "my_agent", "_worker_name": "my_agent"}
```

### 3.2 Feature-by-feature translation

#### Sequential nodes

```python
graph.add_edge("node_a", "node_b")
graph.add_edge("node_b", "node_c")
```

Sequential SIMPLE tasks; state threaded via Conductor expressions (`${node_a.output.state}` → node_b input).

#### LLM nodes (server-side LLM calls)

```python
def analyze(state):
    response = llm.invoke([SystemMessage(...), HumanMessage(state["text"])])
    return {"analysis": response.content}
```

Three-task pipeline with a conditional bypass:

```
prep (SIMPLE)
  → SWITCH(_skip_llm)
      case "true":  INLINE passthrough (pre-computed result)
      default:      LLM_CHAT_COMPLETE → finish (SIMPLE)
  → coalesce (INLINE)
```

1. **Prep worker** swaps the module-level `llm` for a `_LLMCaptureProxy`. When the function calls `llm.invoke(messages)`, the proxy raises `_CapturedLLMCall`, intercepting the messages without an API call. The worker serializes and returns them.
2. **LLM_CHAT_COMPLETE** is a native Conductor system task that calls the provider server-side with the captured messages (server controls model selection, rate limiting, cost tracking).
3. **Finish worker** swaps `llm` for a `_LLMMockProxy` returning the server's response; the function runs to completion, producing the state update as if the call happened normally.
4. **Conditional bypass (SWITCH):** if the function completes *without* calling `llm.invoke()` (e.g. early return), prep sets `_skip_llm: true` and returns the pre-computed result; the SWITCH skips the LLM task.

Thread safety: all LLM variable swaps are protected by `_llm_intercept_lock`.

#### Conditional routing

```python
def route(state):
    if state["sentiment"] == "positive":
        return "celebrate"
    return "console"

graph.add_conditional_edges("analyze", route, {"celebrate": "celebrate", "console": "console"})
```

```
router (SIMPLE) → returns {decision: "celebrate", state: {...}}
  → SWITCH (value-param evaluator on decision)
      case "celebrate": celebrate_tasks...
      case "console":   console_tasks...
  → coalesce (INLINE) — unifies branch outputs
```

#### Parallel branches (FORK_JOIN)

```python
graph.add_edge(START, "pros")
graph.add_edge(START, "cons")
graph.add_edge("pros", "merge")
graph.add_edge("cons", "merge")
```

```
FORK_JOIN
  ├─ branch 0: pros_tasks...
  └─ branch 1: cons_tasks...
JOIN (waits for both)
  → INLINE merge (reducer-aware state combination)
```

State merge: fields with `Annotated[list, operator.add]` are concatenated across branches; all other fields are last-write-wins.

#### Dynamic fan-out (Send API / FORK_JOIN_DYNAMIC)

```python
from langgraph.types import Send

def fan_out(state):
    return [Send("summarize", {"document": doc}) for doc in state["documents"]]

graph.add_conditional_edges("generate", fan_out, ["summarize"])
```

```
router (SIMPLE) → returns {dynamic_tasks: [{node: "summarize", input: {...}}, ...]}
  → INLINE enrich → Conductor FORK_JOIN_DYNAMIC format
  → FORK_JOIN_DYNAMIC (N parallel SIMPLE tasks at runtime)
  → JOIN
  → INLINE merge (reducer-aware, iterates over join output keys)
```

**Detection:** the serializer inspects the routing function's bytecode (`co_names`) for `Send` references; the router worker checks for a list of objects with `.node`/`.arg`. The enrich INLINE maps each `node` to its worker ref and builds the Conductor task format; merge handles a runtime-determined branch count.

#### Cycles and loops (DO_WHILE)

```python
def should_continue(state):
    if state["iterations"] < 3:
        return "refine"   # back-edge → cycle
    return "__end__"      # exit

graph.add_conditional_edges("refine", should_continue, {"refine": "refine", "__end__": END})
```

```
DO_WHILE
  condition: iteration < recursion_limit AND decision in back_edges
  body:
    state_bridge (INLINE) — iter 1 uses pre-loop state, later iters use router output
    ...loop body tasks...
    router (SIMPLE) — evaluates continue/exit
```

**Cycle detection:** during topological traversal, a conditional edge target already visited is a back-edge; tasks between cycle start and the router form the loop body. **State bridge:** selects pre-loop state on iteration 1, router output on iteration 2+. **Recursion limit:** LangGraph `recursion_limit` (default 25) → DO_WHILE iteration cap.

#### Human-in-the-loop

```python
from conductor.ai.agents.frameworks.langgraph import human_task

@human_task(prompt="Review the draft and provide verdict + feedback.")
def review(state):
    pass
```

```
HUMAN task (pauses, waits for external input via API/UI)
  → validation (INLINE)
  → normalization (INLINE)
  → process (SIMPLE) — merges human input into state
```

The decorator marks the function with `_agentspan_human_task = True`. No worker is registered for human nodes; the Conductor HUMAN task type handles input natively, and the server auto-generates the response form schema from the workflow context and prompt. See [agentspan-design.md](agentspan-design.md).

#### State reducers

```python
class State(TypedDict):
    results: Annotated[list, operator.add]  # concatenate across branches
    topic: str                               # last-write-wins
```

The serializer inspects `graph.channels` for `BinaryOperatorAggregate` and maps `operator.add` → `"add"`. Applied in every FORK_JOIN / FORK_JOIN_DYNAMIC merge INLINE:

```javascript
for (var k in branch_state) {
    if (k === 'results') {
        merged[k] = (merged[k] || []).concat(branch_state[k]);   // "add" reducer
    } else {
        merged[k] = branch_state[k];                              // last-write-wins
    }
}
```

#### Retry policies

```python
graph.add_node("fetch", fetch_data, retry=RetryPolicy(max_attempts=3, initial_interval=1.0))
```

- `max_attempts` → `retryCount` (minus 1; Conductor counts retries not attempts)
- `initial_interval` → `retryDelaySeconds`
- `backoff_factor` → `backoffScaleFactor`
- `max_interval` → capped via backoff calculation

#### Agent-as-tool (SUB_WORKFLOW)

```python
from conductor.ai.agents.tool import AgentTool

research_tool = AgentTool(name="researcher", agent=research_graph, description="Research a topic")
main_graph = create_react_agent(llm, tools=[calculator, research_tool])
```

The child agent is recursively compiled into its own workflow def; the parent invokes it as a SUB_WORKFLOW task. `LangGraphNormalizer` detects `AgentTool` (via `_type: "AgentTool"`) and recursively calls `normalize()` on the embedded config.

#### Subgraphs

```python
inner_compiled = inner.compile()

def run_inner(state):
    result = inner_compiled.invoke({"text": state["analysis_text"]})
    return {"sentiment": result["sentiment"], ...}

outer.add_node("analysis", run_inner)
```

Compiled as `SUB_WORKFLOW` with the same intercept pattern as LLM nodes:

1. **Detection:** `_find_subgraph_in_func()` checks node bytecode (`co_names`) against globals for `CompiledStateGraph` objects.
2. **Serialization:** subgraph recursively serialized via `_serialize_graph_structure()` with a `{parent}_{node}` name prefix.
3. **Prep worker:** runs the node with `_SubgraphCaptureProxy`, capturing the `.invoke()` input.
4. **SUB_WORKFLOW:** server compiles the subgraph into a nested `WorkflowDef`, receiving `state` directly via `${workflow.input.state}` and returning both `state` and `result`.
5. **Finish worker:** runs the node with `_SubgraphMockProxy` (returns the SUB_WORKFLOW output state), producing the parent state update.
6. **SWITCH for skip:** handles the case where the function completes without calling `subgraph.invoke()`.

```
prep SIMPLE → SWITCH(_skip_subgraph) → [passthrough INLINE | SUB_WORKFLOW → finish SIMPLE] → coalesce INLINE
```

Subgraph workflows differ from regular graph-structure workflows: input is `${workflow.input.state}` (full state dict), output includes `state` alongside `result`, and the `_graph` metadata is marked `_is_subgraph: true`.

#### State reconstitution

Conductor's JSON serialization loses type information. `_reconstitute_state()` runs before every worker:
- **LangChain Documents:** dicts with a `page_content` key → `Document(page_content=..., metadata=...)`.
- **Stringified dicts:** a single string field containing a dict literal (e.g. `str(state)` used as the prompt) is parsed back via `ast.literal_eval`.

### 3.3 Conductor construct mapping

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
| `create_agent`/`create_react_agent` | AI_MODEL agentic loop | Server-side LLM, with or without tools; system prompt from closure |
| Entire graph (fallback) | Single SIMPLE task | Passthrough: `graph.stream()` locally |

### 3.4 Limitations and unsupported features

This is the source of truth for LangGraph parity.

#### Not supported

| Feature | LangGraph API | Status | Notes |
|---------|--------------|--------|-------|
| `Command` construct | `Command(goto=..., update=...)` | Not implemented | Dynamic routing with state updates. Planned (Task #42). |
| Custom reducers | `Annotated[list, my_custom_fn]` | Warning logged | Only `operator.add` is mapped. Custom callables fall back to last-write-wins in FORK_JOIN merge (possible data loss). |
| Functional API | `@entrypoint`, `@task` | Not implemented | Different programming model entirely. |
| `CachePolicy` | `CachePolicy(ttl=...)` | Not implemented | No equivalent in Conductor task model. |
| Managed values | `RemainingSteps`, `IsLastStep` | Not implemented | Depend on LangGraph internal recursion tracking. |
| Private state channels | `PrivateAttr`, channel-level access control | Not implemented | Conductor state is a flat JSON dict. |
| `InputState` / `OutputState` distinction | Separate TypedDict for input vs output | Not implemented | Single state schema; no input validation / output filtering. |
| Time travel / replay | `get_state_history()`, replay from checkpoint | Not implemented | No checkpoint storage. |
| Cross-thread persistence | `BaseStore`, `InMemoryStore` | Not implemented | No cross-execution memory store. |
| `InjectedState` / `InjectedStore` | Tool parameter injection | Not implemented | Tools receive explicit inputs only. |
| `ValidationNode` | Built-in validation node type | Not implemented | Use regular nodes with validation logic. |
| Middleware | Request/response middleware hooks | Not implemented | No equivalent in Conductor. |
| Deferred nodes | `defer=True` | Not implemented | All nodes execute eagerly. |
| LangGraph Platform features | Cron jobs, double texting, assistants API | Not applicable | LangGraph Cloud features, not graph features. |
| CompiledStateGraph as tool parameter | Passing a graph object directly as a tool | Not supported | `ToolNode` rejects non-callable tools. Wrap in a `@tool` that calls `.invoke()`. |
| Server-side token streaming | Real-time token streaming from LLM nodes | Not supported | `LLM_CHAT_COMPLETE` returns the full response. |

#### Passthrough only (local execution)

These run, but the whole graph executes inside one SIMPLE worker — the server has no per-node visibility, cannot control LLM calls, and cannot orchestrate steps. See §2.

| Feature | Why Passthrough | What Triggers It |
|---------|----------------|------------------|
| Graphs where no model can be detected | Serializer can't find LLM object via introspection | No object with `model_name`/`model` attribute in graph nodes or globals |
| Nodes with >1 positional arg in custom StateGraphs | Cannot run as standalone SIMPLE workers | Function signature like `(state, config)` |

**Previously passthrough, now server-side:** `create_agent` graphs (with or without tools/system prompt) are now detected as full extraction — the model is extracted from graph nodes and the system prompt from `model_node`'s closure (`system_message` free variable).

#### Known limitations of supported features

**Bytecode inspection for detection (LLM, subgraph, Send API).** Detection relies on CPython bytecode (`func.__code__.co_names` + `func.__globals__`). It breaks with: aliased imports (`ChatOpenAI as MyLLM`), variables captured in closures, decorators that replace `__code__`, and non-CPython runtimes (PyPy, GraalPy). Mitigation: use straightforward module-level LLM/subgraph variable assignments; avoid aliasing or wrapping.

**Global variable mutation for LLM/subgraph interception.** Prep/finish workers swap module-level globals with proxies under a process-wide lock (`_llm_intercept_lock`): one node function at a time per process; functions sharing an LLM variable share the lock; on error the `finally` restores the original, but a brief window exists where another thread could see the proxy. Safe for the current single-threaded worker model; would need redesign for concurrent execution.

**State reducers.** Only `operator.add` maps to array concat. Other fields use last-write-wins. Custom reducer callables are detected and a warning logged, but the server cannot run arbitrary Python in JavaScript INLINE tasks.

**Retry policies.** `max_attempts`, `initial_interval`, `backoff_factor` are mapped. `max_interval` (backoff is unbounded) and `jitter` are not mapped and log a warning.

**Multiple conditional edges from the same source node.** Targets are merged but the last router function wins (Conductor SWITCH evaluates one decision per node); a warning is logged.

**Result extraction heuristic.** The workflow extracts "result" from the final node's state using `result`, `final_report`, `output` in that order. A different field name yields empty workflow output (full state is always available via the state output).

**INLINE JavaScript in Conductor tasks.** Merge/bridge/coalesce/enrich logic runs as GraalJS, string-concatenated in Java with no compile-time validation; covered by integration tests, no unit tests for the generated JavaScript.

### 3.5 Data flow

```
User Code                    Python SDK                     Server
─────────                    ──────────                     ──────
StateGraph / create_agent    serialize_langgraph()
  │                            ├─ Introspect graph
  │                            ├─ Extract nodes/edges
  │                            ├─ Build worker functions
  │                            ├─ Produce raw_config
  │                          AgentRuntime.run()
  │                            ├─ POST /agent/start ────────► LangGraphNormalizer.normalize()
  │                            │   (raw_config + framework)    ├─ Detect path (full/graph/passthrough)
  │                            │                               ├─ Build AgentConfig
  │                            │                             AgentCompiler.compile()
  │                            │                               ├─ Build Conductor WorkflowDef
  │                            │                               ├─ Register workflow
  │                            │                               └─ Start execution
  │                            ├─ Register workers           ◄─ Conductor polls workers
  │                            ├─ Workers execute:
  │                            │   node_func / router_func / llm_prep/finish
  │                            ├─ Poll for completion
  ◄────────────────────────────┤ Return result
```

---

## 4. LangChain (passthrough via LangGraph)

Modern LangChain (v1.2+) uses `create_agent()` from `langchain.agents`, which returns a `CompiledStateGraph`. AgentSpan detects this as a LangGraph object and routes it through the LangGraph pipeline (§3) — so LangChain agents get the same server-side LLM orchestration, tool extraction, and system-prompt support as native LangGraph agents.

```
create_agent(llm, tools=[...], system_prompt="...")
    → CompiledStateGraph ──detect_framework()──► "langgraph"
    → serialize_langgraph()
        ├─ _find_model_in_graph()              → "openai/gpt-4o-mini"
        ├─ _find_tools_in_graph()              → [tool1, tool2, ...]
        └─ _extract_system_prompt_from_graph() → "You are a helpful assistant."
    → Full Extraction raw_config: { name, model, instructions, tools: [...] }
    → Server: LangGraphNormalizer → AgentCompiler → Conductor WorkflowDef (AI_MODEL)
```

| Path | When | Conductor Pattern |
|------|------|-------------------|
| **Full extraction (with tools)** | `create_agent(llm, tools=[...])` | AI_MODEL loop + SIMPLE per tool |
| **Full extraction (no tools)** | `create_agent(llm, tools=[])` | AI_MODEL single LLM call |
| **Passthrough** | Legacy `AgentExecutor` (if model/tools undetectable) | Single SIMPLE task running executor locally |

### 4.1 Feature support

- **System prompts** passed via `create_agent(llm, system_prompt="...")` are extracted from the `model_node` closure (`_extract_system_prompt_from_graph()` finds the `system_message` free variable) and sent as `instructions`.
- **Tools** — `@tool` functions and `StructuredTool` objects are extracted and registered as individual workers; the server orchestrates tool calling through the AI_MODEL loop. Name, description, and JSON schema (type hints or Pydantic `args_schema`) are included.
- **Structured output** — `with_structured_output()` works inside `@tool` functions; the structured LLM call runs locally within the tool worker while the outer loop is server-side.
- **Prompt templates** — `ChatPromptTemplate`/`PromptTemplate` work by formatting the system prompt before passing it to `create_agent`; the formatted string is sent as `instructions`.
- **Multi-turn** — handled via AgentSpan session management; each `runtime.run()` call is independent (no checkpointer).

Since `create_agent` returns a `CompiledStateGraph`, LangChain agents are a subset of the LangGraph integration — all §3 features and limitations apply.

### 4.2 Legacy AgentExecutor support

The `langchain.py` serializer handles legacy `AgentExecutor` objects two ways:
1. **Full extraction** — if model and tools are extractable (`executor.agent.llm`, `executor.tools`), delegates to the shared `_serialize_full_extraction()`.
2. **Passthrough** — fallback: the executor runs inside one SIMPLE worker with an `AgentspanCallbackHandler` streaming `tool_call`/`tool_result` events (see §2). `LangChainNormalizer` produces a passthrough `AgentConfig` with `_framework_passthrough: true`.

Note: `AgentExecutor` is no longer importable from current LangChain (v1.2+). Use `create_agent`.

### 4.3 LangChain-specific limitations

Inherited: all §3.4 limitations (custom reducers, `Command`, functional API, time travel, cross-thread persistence).

| Feature | Status | Notes |
|---------|--------|-------|
| `AgentExecutor` | Deprecated | No longer importable; use `create_agent`. |
| LCEL chains (non-agent) | Not supported | Only `CompiledStateGraph` is detected. Wrap plain LCEL (`prompt \| llm \| parser`) in a `@tool` or use inside `create_agent`. |
| `ConversationBufferMemory` | Not applicable | Legacy memory classes don't apply to `create_agent`; use tool-based memory. |
| LangServe | Not applicable | AgentSpan replaces LangServe for deployment. |
| LangSmith tracing | Compatible | LangSmith callbacks work inside tool workers alongside `AgentspanCallbackHandler`. |

---

## 5. OpenAI Agents SDK and Google ADK

Both are first-class bridges that **decompose** to native server-side tasks. Detection is duck-typed; no framework is imported by AgentSpan, and the framework packages are optional peer dependencies. See [Python framework-agents.md](../sdk/python/docs/framework-agents.md) and [TypeScript framework-agents.md](../sdk/typescript/docs/framework-agents.md) for full usage.

### 5.1 OpenAI Agents SDK

An `@openai/agents` (TS) / `agents` (Python) `Agent` is extracted into an AI_MODEL agentic loop plus one SIMPLE task per tool — identical to LangGraph full extraction. Detection (TS): `name` + string/function `instructions` + string `model` + `tools[]` + an OpenAI marker (`handoffs[]`, `inputGuardrails[]`, `asTool()`, `toolUseBehavior`, ...).

Two authoring styles:
- **Drop-in `Runner`** (Python) — change one import to `from conductor.ai import Runner` and keep your existing `agents.Agent`. `Runner.run` / `run_sync` / `run_streamed` accept an OpenAI-Agents `Agent` or a native AgentSpan `Agent`; `RunResult` exposes `.final_output` and `.execution_id` (`context` is accepted for compatibility and ignored). `from conductor.ai import function_tool` aliases `@tool`.
- **Pass to `runtime.run(...)`** (TS and Python) — hand the `Agent` straight to the runtime; same entry point as every other framework.

### 5.2 Google ADK

A `@google/adk` agent is bridged via the TypeScript SDK. Detection: `subAgents[]` (orchestration agents — `Sequential`/`Parallel`/`Loop`), or string `model` + ADK markers (`instruction`, `outputKey`, `generateContentConfig`, `beforeModelCallback`, ...). An `LlmAgent` extracts to an AI_MODEL loop + tool tasks; the orchestration agents map their structure onto Conductor tasks. Pass the agent straight to `runtime.run(...)`.

```ts
import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

const agent = new LlmAgent({ name: 'greeter', model: 'gemini-2.5-flash',
  instruction: 'You are a friendly assistant.' });
const runtime = new AgentRuntime();
const result = await runtime.run(agent, 'Say hello and a fun fact about ML.');
```

> The TypeScript SDK additionally bridges the **Vercel AI SDK** (AI SDK `tool()` objects auto-convert to native tool defs; a drop-in `generateText`/`streamText` subpath builds an `Agent` under the hood). See [TypeScript framework-agents.md](../sdk/typescript/docs/framework-agents.md).

---

## 6. Claude Agent SDK (passthrough by design)

The Claude Agent SDK (`claude_agent_sdk`) is a full runtime — built-in tools (Read, Edit, Bash, ...), hooks, sessions, permissions. Extracting individual tools would lose most of its value, so AgentSpan runs it **passthrough**: the full `query()` runs in one durable Conductor SIMPLE worker (the §2 passthrough architecture), instrumented through the SDK's hook system. Users pass `ClaudeAgentOptions` (or use the native `ClaudeCode` model on an AgentSpan `Agent`) to `runtime.run()` / `runtime.start()`.

**Use cases:** (A) bring existing Claude Agent SDK agents in for durability/orchestration/observability; (C) invoke a Claude Agent SDK agent as a worker tool inside a larger AgentSpan workflow.

### 6.1 Execution model

```
runtime.run(options, prompt)
  ├─ detect_framework() → "claude_agent_sdk"   (type-name check on ClaudeAgentOptions)
  ├─ serialize_claude_agent_sdk(options) → (raw_config={name,_worker_name}, [WorkerInfo])
  ├─ _build_passthrough_func() → make_claude_agent_sdk_worker()   (closure: options, server_url, auth)
  ├─ _register_passthrough_worker() → Conductor task def (600s timeout)
  └─ POST /api/agent/start {framework, rawConfig}
        → ClaudeAgentSdkNormalizer → AgentConfig (_framework_passthrough=true)
        → AgentCompiler.compileFrameworkPassthrough() → WorkflowDef (single SIMPLE task)
        → start execution → Conductor → worker polls task:
            1. extract cwd from task input (set on options so file ops run in the right dir)
            2. inject execution credentials → os.environ (cleanup in finally)
            3. create metadata dict {tool_call_count, tool_error_count, subagent_count, tools_used}
            4. build agentspan hooks (close over metadata + execution_id)
            5. merge user hooks + agentspan hooks (user first)
            6. asyncio.run(_run_query(prompt, merged_options))
               └─ async for message in query(prompt, options):
                    ├─ hooks fire: PreToolUse, PostToolUse, SubagentStart, ...
                    │   ├─ push stream events: POST /api/agent/events/{executionId}
                    │   └─ mutate metadata
                    └─ collect ResultMessage → result text + token usage
            7. return TaskResult {result, tools_used, ...metadata, token_usage}
```

### 6.2 Hooks (observability + metadata)

All agentspan hooks are defensive (try/except) and return `{}` (no interference). User hooks run first; agentspan hooks are appended. Event delivery is fire-and-forget via the shared `ThreadPoolExecutor` (§2).

| Hook Event | Stream Event | Metadata Mutation |
|---|---|---|
| `PreToolUse` | `{type: "tool_call", toolName, toolUseId}` | `tool_call_count += 1`, `tools_used.add(name)` |
| `PostToolUse` | `{type: "tool_result", toolName, toolUseId}` | — |
| `PostToolUseFailure` | `{type: "tool_error", toolName, error}` | `tool_error_count += 1` |
| `SubagentStart` | `{type: "subagent_start", agent_id}` | `subagent_count += 1` |
| `SubagentStop` | `{type: "subagent_stop", agent_id}` | — |
| `Notification` | `{type: "notification", message}` | — |
| `Stop` | `{type: "agent_stop"}` | — |

The exact hook callback signature must be verified against the installed `claude-agent-sdk` version (PyPI: `claude-agent-sdk`; imports `query`, `ClaudeAgentOptions`, `AssistantMessage`, `ResultMessage`). `ClaudeAgentOptions` is kept in the worker closure, never JSON-serialized (it may contain callables).

### 6.3 Components, design decisions, limitations

| Component | File |
|---|---|
| Detection + serialize short-circuit | `sdk/python/src/agentspan/agents/frameworks/serializer.py` |
| Serializer, worker, hooks | `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py` (new) |
| `_build_passthrough_func()` branch | `sdk/python/src/agentspan/agents/runtime/runtime.py` |
| Passthrough normalizer | `server/.../normalizer/ClaudeAgentSdkNormalizer.java` (new) |

Key decisions: passthrough over extraction (full runtime — extraction loses value); hooks for observability (exact instrumentation points, additive, defensive); `asyncio.run()` in the sync worker (fresh loop per worker thread); options in closure not JSON (callables); user hooks run first.

**Use case C.** Phase 1 (ships with A): wrap the SDK in an AgentSpan `@tool` that drives `query()` — works today, but no SUB_WORKFLOW and no inner-agent streaming. Phase 2 (follow-up): `runtime.register(options, name=...)` registers the agent by name for native handoffs (`HandoffCondition(target="claude_reviewer")`) with full SUB_WORKFLOW composition and streaming.

**Limitations.** `asyncio.run()` fails inside an already-running loop (Jupyter) — use `nest_asyncio` or a separate thread. Phase 1 `@tool` produces no SUB_WORKFLOW / inner events. Hooks capture tool-level events but not individual LLM API calls (the SDK exposes no LLM-call hook). TypeScript support is a follow-up (Python first).

---

## 7. OCG retrieval integration

OCG (Open Context Graph) is a retrieval engine over a knowledge graph of entities — messages, channels, people, tickets — linked by claims and relationships. It is embedding/keyword search exposed as an HTTP API, **not** an LLM.

The integration lives **entirely in the Python SDK** (`agentspan.agents.ocg`): the retrieval system prompt, tool schemas, endpoint routing, and instance binding. The tools compile to plain Conductor HTTP tasks, so **any AgentSpan server runs them with zero OCG-specific configuration** — no properties, no task types. OCG is opt-in per agent; an agent that doesn't declare OCG tools never makes an OCG call.

### 7.1 Two shapes

**Sub-agent — delegate retrieval.** `ocg_agent()` returns an ordinary `Agent` carrying the canned retrieval prompt and the `ocg_*` tools. Wrap it with `agent_tool()` and the main agent's LLM sees a single tool; calling it runs the retriever as a sub-workflow with its own LLM loop, returning one synthesized, cited answer. The raw citations stay in the retriever's context; the main agent only sees the synthesized answer. Choose this when retrieval takes judgment (several queries, neighborhood walks, two-step aggregation).

```python
from conductor.ai.agents import Agent, agent_tool
from conductor.ai.agents.ocg import ocg_agent

retriever = ocg_agent(
    model="openai/gpt-4o-mini",
    url="https://test.contextgraph.io",
    credential="OCG_PUBLIC_KEY",        # secrets-store NAME, never the key
)
main = Agent(
    name="support", model="openai/gpt-4o",
    instructions="Call your retrieval tool exactly once with the user's full question; its answer is complete — write a concise cited brief.",
    tools=[agent_tool(retriever)], max_turns=4,
)
```

**Direct tools — the main agent queries itself.** `ocg_tools()` returns the raw `ToolDef`s; attach them (or a subset) to your own agent and its LLM issues the queries directly — no sub-workflow hop, roughly half the tokens for simple lookups, but raw citations land in the main agent's context and the retrieval prompting is yours.

```python
from conductor.ai.agents.ocg import ocg_tools

main = Agent(
    name="support", model="openai/gpt-4o-mini",
    instructions="Answer using ocg_query (keyword/embedding retrieval, NOT an LLM). Query with specific keywords, at most one per topic, then write your brief.",
    tools=ocg_tools(url="https://test.contextgraph.io", credential="OCG_PUBLIC_KEY",
                    entities=False, memory=False),   # subset switches → ocg_query only
    max_turns=6,
)
```

### 7.2 How a tool call executes

There is no OCG code on the server. The SDK bakes everything the dispatch needs into each tool's config at definition time; the compiled workflow's **enrich script** (compile-time JavaScript, evaluated at dispatch) turns the LLM's arguments into a standard Conductor HTTP task.

```
SDK: ToolDef(tool_type="http", config={url, method, pathTemplate, queryParams,
             headers:{Authorization:"Bearer ${OCG_PUBLIC_KEY}"}})
  → Compiler bakes config into workflow def (placeholder escaped for the host's resolver)
  → LLM emits a tool call, e.g. ocg_get_entity(entity_id="entity_01...", depth=1)
  → Enrich script: uri = url + pathTemplate filled from args (URL-encoded) + queryParams present in args;
                   body = remaining args (consumed args removed)
  → HTTP task {uri, method, headers, body}
  → Conductor resolves credential placeholder by NAME from secrets store (token in memory only)
  → HTTPS request to OCG instance → JSON response → tool result for the LLM
```

Key properties:
- **Per-tool instance binding.** `url=` is required — every OCG tool set binds the instance it talks to. Different agents can target different graphs (e.g. a US retriever and a Canada retriever in one router agent); agents bound to different instances must have distinct `name`s.
- **Secrets never leave the server.** `credential="OCG_PUBLIC_KEY"` is a *name*; it compiles to a standard HTTP-tool header placeholder resolved from the server's secrets store at execution. Store it once (`PUT /api/secrets/OCG_PUBLIC_KEY`). This is the same credential contract as every other tool — see [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md).
- **Path templating is generic.** `pathTemplate`/`queryParams` on an `http` tool config is a general AgentSpan capability; OCG is its first user.

### 7.3 The tools

| Tool (LLM-visible)     | Endpoint                                 | Method   |
| ---------------------- | ---------------------------------------- | -------- |
| `ocg_query`            | `/api/v1/agent/query`                    | `POST`   |
| `ocg_get_entity`       | `/api/v1/entities/{entity_id}`           | `GET`    |
| `ocg_neighborhood`     | `/api/v1/graph/neighborhood/{entity_id}` | `GET`    |
| `ocg_memory_set`       | `/api/v1/memories`                       | `POST`   |
| `ocg_memory_reinforce` | `/api/v1/memories/{key}/reinforce`       | `POST`   |
| `ocg_memory_delete`    | `/api/v1/memories/{key}`                 | `DELETE` |

Path params (`{entity_id}`, `{key}`) are filled from the LLM's arguments and URL-encoded; listed query params are appended when present; everything else becomes the JSON body. Subset switches on `ocg_tools()` / `ocg_agent()`: `query`, `entities` (get_entity + neighborhood), `memory` (set / reinforce / delete).

### 7.4 Keeping the LLM honest

OCG responses are injected verbatim into the calling LLM's context, so schemas and the canned prompt enforce discipline:
- `max_results` carries a schema-level `maximum: 100` (default 10); the prompt recommends ≤ 25.
- `traversal_level` defaults to `0` (citations only) — each level multiplies response size.
- `start_time`/`end_time` must be full RFC3339 (`2026-06-04T00:00:00Z`); the OCG API rejects bare dates, and the schemas say so to prevent retry loops.
- The canned retrieval prompt budgets at most 3 distinct keyword queries per request, forbids rephrasing (embedding search returns the same results for the same intent), anchors relative dates on an execution-time `__today__`, and instructs keyword-style queries under ~15 content words.

`ocg_agent()` defaults to `max_turns=10`; give your *main* agent explicit retrieval instructions and a small `max_turns` so it treats the retriever's answer as complete instead of paging for continuations.

For full parameter tables see [Python SDK API Reference → ocg_agent() / ocg_tools()](../sdk/python/docs/api-reference.md).
