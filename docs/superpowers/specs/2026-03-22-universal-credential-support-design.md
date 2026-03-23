# Universal Credential Support Design

**Date:** 2026-03-22
**Status:** Draft
**Topic:** Extend credential management to all tool types and framework integrations

---

## Problem Statement

The credential management system (execution token minting, `/api/credentials/resolve`, `SubprocessIsolator`) works for `@tool` worker functions, CLI tools, and code execution tools. But several tool types and framework integrations have no credential support:

- `http_tool()` and `mcp_tool()` have static headers — can't reference per-user secrets
- LangGraph, LangChain, OpenAI Agent SDK, and Google ADK passthrough workers don't resolve credentials
- Framework-extracted tools (via `_register_framework_workers`) have no credential metadata
- External workers (`@tool(external=True)`) have no documented credential resolution path

This design extends the existing credential pipeline to cover every tool type universally.

---

## Design Principles

1. **`credentials=[...]` works everywhere.** Same declaration syntax on every tool type.
2. **Server-side tools get server-side resolution.** HTTP and MCP tools run as Conductor system tasks on the Java server — credential substitution happens in Java, not Python.
3. **SDK-side tools get SDK-side resolution.** Worker tools, framework passthrough, and extracted tools resolve credentials via `WorkerCredentialFetcher`.
4. **Test-first, e2e only.** Every change is verified by an end-to-end test against a real server. No mocks for integration boundaries.
5. **No magic.** Credentials are always explicitly declared, never guessed.
6. **Resolved credential values never persist.** No credential values in Conductor task input/output stored to DB. Resolution happens at execution time only.

---

## What's Already Covered (no work needed)

| Tool Type | Why It Works |
|-----------|-------------|
| `@tool` (worker) | Full pipeline: `ToolDef.credentials` → execution token → `/api/credentials/resolve` → env injection |
| CLI tools (`run_command`) | Agent-level credentials propagated to CLI tool's `ToolDef` |
| Code execution tools | Same propagation as CLI tools |
| `agent_tool()` / sub-agents | Token forwarded via `compileSubAgent()` and enrichment script |
| Media tools (image/audio/video) | Server system tasks, `AIModelProvider` resolves LLM keys per-user |
| RAG tools (index/search) | Server system tasks, `VectorDBProvider` handles auth |
| `human_tool()` | No credentials needed |
| LLMGuardrail | Compiles to server-side `LLM_CHAT_COMPLETE`, uses `AIModelProvider` |
| RegexGuardrail | Pure regex, no credentials |
| Custom `@guardrail` | Pure validation logic |
| `pdf_tool()` | No external API needed |

---

## Gap 1: `http_tool()` Credential Binding

### Current State

```python
http_tool(
    name="github_api",
    url="https://api.github.com/repos",
    headers={"Authorization": "Bearer sk-hardcoded"},  # static, baked into workflow
)
```

### Target State

```python
http_tool(
    name="github_api",
    url="https://api.github.com/repos",
    headers={"Authorization": "Bearer ${GITHUB_TOKEN}"},
    credentials=["GITHUB_TOKEN"],
)
```

### Two Data Flows

The `credentials` parameter serves two purposes that flow through different paths:

1. **Token minting path:** `ToolDef.credentials` → `config_serializer` → `ToolConfig.config.credentials` → `extractDeclaredCredentials` → execution token `declared_names`. This ensures the token authorizes resolution of these credential names. **Already implemented.**

2. **Header substitution path:** `${NAME}` patterns in `config.headers` → serialized as-is into workflow definition → at HTTP task execution time, Java server resolves placeholders using `CredentialResolutionService`. **New work.**

### SDK Changes

- `tool.py`: Add `credentials` param to `http_tool()`, pass to `ToolDef(credentials=...)`
- `tool.py`: Add SDK-side validation that every `${NAME}` pattern in headers has a matching entry in `credentials=[]`. Raises `ValueError` at definition time on mismatch.
- `config_serializer.py`: No change needed — already serializes `ToolDef.credentials` into `config.credentials`
- Headers with `${...}` patterns are serialized as-is (plain strings) — no special handling needed

### Server-Side Changes

**Integration point:** The GraalJS enrichment script cannot call Spring beans. Credential resolution must happen in Java code that intercepts HTTP task execution.

**Approach: Custom `CredentialAwareHttpTask`** that extends Conductor's `HttpTask`:

```java
@Component
public class CredentialAwareHttpTask extends HttpTask {

    private final ExecutionTokenService tokenService;
    private final CredentialResolutionService resolutionService;

    @Override
    public boolean execute(WorkflowModel workflow, TaskModel task, WorkflowExecutor executor) {
        // Resolve ${NAME} patterns in headers before HTTP execution
        Map<String, Object> input = task.getInputData();
        Object httpRequest = input.get("http_request");
        if (httpRequest instanceof Map<?,?> reqMap) {
            Object headers = reqMap.get("headers");
            Object ctx = input.get("__agentspan_ctx__");
            if (headers instanceof Map<?,?> headerMap && ctx != null) {
                Map<String, String> resolved = resolveHeaders(headerMap, ctx);
                ((Map) reqMap).put("headers", resolved);
            }
        }
        return super.execute(workflow, task, executor);
    }

    private Map<String, String> resolveHeaders(Map<?,?> headers, Object ctx) {
        // Extract token from ctx
        String token = null;
        if (ctx instanceof Map<?,?> ctxMap) {
            token = (String) ctxMap.get("execution_token");
        } else if (ctx instanceof String s) {
            token = s;
        }
        if (token == null) return (Map<String, String>) headers;

        TokenPayload payload = tokenService.validate(token);
        Map<String, String> result = new LinkedHashMap<>();
        Pattern p = Pattern.compile("\\$\\{(\\w+)}");

        for (Map.Entry<?,?> entry : headers.entrySet()) {
            String value = String.valueOf(entry.getValue());
            Matcher m = p.matcher(value);
            StringBuilder sb = new StringBuilder();
            while (m.find()) {
                String credName = m.group(1);
                String credValue = resolutionService.resolve(payload.userId(), credName);
                m.appendReplacement(sb, Matcher.quoteReplacement(credValue != null ? credValue : ""));
            }
            m.appendTail(sb);
            result.put(String.valueOf(entry.getKey()), sb.toString());
        }
        return result;
    }
}
```

**Enrichment script change:** The enrichment script already passes `$.agentspanCtx` to SIMPLE tasks. Extend the HTTP task branch to also include `__agentspan_ctx__`:

```javascript
// In enrichToolsScript, HTTP branch:
if (httpCfg[n]) {
    // ... existing header setup ...
    if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }
}
```

**Security:** Resolved credential values exist only in the in-memory `inputData` during execution. Conductor's `HttpTask` does not persist resolved headers back to the task model. The `${NAME}` placeholders remain in the workflow definition.

### Test

```python
# tests/e2e/test_http_tool_credentials.py

# 1. Start a tiny HTTP echo server (returns received headers as JSON)
# 2. Store _TEST_HTTP_CRED credential on server via REST API
# 3. Create agent with:
#    http_tool(
#        name="echo_api",
#        url=f"http://localhost:{port}/echo",
#        headers={"X-Test-Auth": "Bearer ${_TEST_HTTP_CRED}"},
#        credentials=["_TEST_HTTP_CRED"],
#    )
# 4. Compile agent via /api/agent/compile — verify ${...} in workflow def
# 5. Run agent, prompt LLM to call the tool
# 6. Echo server verifies: received header "X-Test-Auth: Bearer <resolved_value>"
# 7. Verify workflow output contains the echo response
# 8. Cleanup: delete test credential
```

---

## Gap 2: `mcp_tool()` Credential Binding

### Design

Identical pattern to `http_tool()`. MCP tools use `CALL_MCP_TOOL` system task which makes HTTP calls to the MCP server with headers from `configParams.headers`.

### Changes

- `tool.py`: Add `credentials` param to `mcp_tool()`, same validation as `http_tool()`
- Server: Same `CredentialAwareHttpTask` pattern, or a separate `CredentialAwareMcpTask` that extends `CallMcpToolTask`
- Enrichment script: Pass `__agentspan_ctx__` to MCP task branch (same as HTTP)

### Test

Same echo-server pattern — MCP test server verifies resolved headers arrived.

---

## Gap 3: Framework Passthrough Credentials (LangGraph, LangChain, OpenAI Agent SDK, Google ADK)

### Current State

```python
graph = create_react_agent(model, tools)
with AgentRuntime() as runtime:
    result = runtime.run(graph, "prompt")  # no way to declare credentials
```

### Target State

```python
with AgentRuntime() as runtime:
    result = runtime.run(graph, "prompt", credentials=["GITHUB_TOKEN", "OPENAI_API_KEY"])
```

### How It Works

1. **SDK** (`runtime.py`): `run()`, `start()`, and `stream()` accept `credentials` kwarg
2. **SDK** (`runtime.py`): Credentials included in the workflow start request payload
3. **Server** (`AgentService.java`): For framework agents, the start request carries credentials in the input. `AgentService` reads them and includes in execution token `declared_names` — **in addition to** any credentials extracted from the agent config.
4. **Server**: Token embedded in workflow input as `__agentspan_ctx__` (already done)
5. **SDK passthrough workers**: Before invoking graph/executor:
   - Extract execution token from task input
   - Read credential names from a workflow-level registry (see Gap 4)
   - Call `WorkerCredentialFetcher.fetch(token, credential_names)`
   - Inject resolved credentials into `os.environ`
   - Invoke graph/executor
   - Clean up env vars after completion

### Thread Safety

Passthrough workers run in Conductor's thread pool, not in separate processes. Injecting into `os.environ` is not thread-safe if multiple tasks run concurrently.

**Mitigation:** Conductor workers are configured with `thread_count=1` by default. Passthrough workers use `_passthrough_task_def` which also defaults to `thread_count=1`. With a single thread, there is no concurrency risk.

**Documented limitation:** If users increase `thread_count` on passthrough workers, concurrent credential injection may cause cross-contamination. This should be documented as a known constraint — or we enforce `thread_count=1` for credential-bearing passthrough workers.

### Framework-Specific Changes

All four frameworks follow the same pattern. The credential injection point varies:

| Framework | Worker Builder | Injection Point |
|-----------|---------------|-----------------|
| LangGraph | `make_langgraph_worker()` in `frameworks/langgraph.py` | Before `graph.stream()` / `graph.invoke()` |
| LangChain | `make_langchain_worker()` in `frameworks/langchain.py` | Before `executor.invoke()` |
| OpenAI Agent SDK | Generic path via `_register_framework_workers()` | In `make_tool_worker()` via workflow credential fallback (Gap 4) |
| Google ADK | Generic path via `_register_framework_workers()` | Same as OpenAI |

### SDK Changes

- `runtime.py`: `run()`, `start()`, `stream()` accept `credentials` kwarg
- `runtime.py`: `_start_via_server()` and `_start_framework_via_server()` include credentials in request
- `frameworks/langgraph.py`: `make_langgraph_worker()` — add credential resolution + env injection
- `frameworks/langchain.py`: `make_langchain_worker()` — same
- Server `AgentService.java`: When starting workflow, read `credentials` from start request input, include in token minting

### Test

```python
# Create LangGraph agent with a tool that returns os.environ.get("_TEST_FW_CRED")
# Store _TEST_FW_CRED on server
# Run: runtime.run(graph, "call the tool", credentials=["_TEST_FW_CRED"])
# Verify tool output contains the resolved credential value
```

---

## Gap 4: Framework-Extracted Tool Credentials

### Problem

When `_register_framework_workers()` extracts individual tools from a framework agent and registers them as Conductor workers, the `WorkerInfo` objects don't carry credential metadata. `make_tool_worker()` has no `tool_def`, so `credential_names` is empty.

### Design

Add a workflow-level credential registry. When `credentials=[...]` is passed on `run()`, ALL tools in that workflow inherit those credentials as a fallback.

```python
# In _dispatch.py
_workflow_credentials = {}  # workflow_instance_id -> list[str]
_workflow_credentials_lock = threading.Lock()
```

In `tool_worker()`, after checking `_tool_def` sources:

```python
if not credential_names and task.workflow_instance_id:
    with _workflow_credentials_lock:
        credential_names = _workflow_credentials.get(task.workflow_instance_id, [])
```

### Lifecycle

- **Populate:** `runtime.py` sets `_workflow_credentials[workflow_id] = credentials` after `_start_via_server()` returns the workflow ID
- **Cleanup:** `runtime.py` deletes the entry in `_poll_status_until_complete()` after workflow finishes (in a `finally` block)
- **Thread safety:** Protected by `threading.Lock` for read/write

### SDK Changes

- `_dispatch.py`: Add `_workflow_credentials` dict with lock, use as fallback in credential resolution
- `runtime.py`: Populate after workflow start, clean up after completion

### Test

```python
# Extract tools from a framework agent, register as workers
# Run with credentials=["_TEST_EXTRACTED_CRED"]
# Verify extracted tool receives the credential via workflow fallback
```

---

## Gap 5: External Workers

### Problem

`@tool(external=True)` workers run in separate processes. They receive task input from Conductor but don't know how to resolve credentials.

### Design

No new infrastructure needed — the execution token is already in `__agentspan_ctx__` in the task input (via enrichment script). External workers call `/api/credentials/resolve` directly.

### Changes

- **Documentation:** Add section to `AGENTS.md` explaining credential resolution for external workers
- **Helper function:** `agentspan.agents.resolve_credentials(input_data, names)` thin wrapper:

```python
def resolve_credentials(input_data: dict, names: list) -> dict:
    """Resolve credentials from Conductor task input data. For external workers."""
    from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
    from agentspan.agents.runtime.config import AgentConfig

    # Extract token from __agentspan_ctx__
    token = None
    ctx = input_data.get("__agentspan_ctx__")
    if isinstance(ctx, dict):
        token = ctx.get("execution_token")
    elif isinstance(ctx, str):
        token = ctx

    config = AgentConfig.from_env()
    fetcher = WorkerCredentialFetcher(server_url=config.server_url)
    return fetcher.fetch(token, names)
```

### Test

```python
# Store credential on server
# Create agent with @tool(external=True, credentials=["_TEST_EXT_CRED"])
# Start workflow
# Simulate external worker: fetch task from Conductor API, call resolve_credentials()
# Verify credential returned
```

---

## Implementation Order

Each phase is fully tested before moving to the next.

| Phase | Gap | Execution | Test Strategy |
|-------|-----|-----------|---------------|
| **1** | `http_tool()` credential binding | Server-side Java | Echo HTTP server verifies resolved headers |
| **2** | `mcp_tool()` credential binding | Server-side Java | Same pattern with MCP headers |
| **3** | Framework passthrough `run(credentials=[...])` | SDK-side Python | LangGraph/LangChain tool reads resolved env var |
| **4** | Workflow-level credential fallback | SDK-side Python | OpenAI/ADK extracted tool reads resolved env var |
| **5** | External worker helper + docs | Documentation + helper | External worker calls resolve API |
| **6** | Full validation | Both | Run all credential examples against live server |

### Phase execution protocol

For every phase:

1. **Write e2e test FIRST** — must fail before implementation
2. **Implement the fix** — minimal changes, no over-engineering
3. **Run the new test** — must pass
4. **Run ALL existing credential tests** — Python `tests/e2e/` + `tests/unit/` + Java `./gradlew test`
5. **Run a real example** against live server
6. **Only then move to next phase**

---

## Files Changed Summary

### Python SDK

| File | Change |
|------|--------|
| `tool.py` | Add `credentials` param to `http_tool()` and `mcp_tool()`, validate `${NAME}` matches |
| `runtime.py` | `run()`/`start()`/`stream()` accept `credentials` kwarg, populate `_workflow_credentials` |
| `_dispatch.py` | Add `_workflow_credentials` with lock, use as fallback for extracted framework tools |
| `frameworks/langgraph.py` | Credential resolution + env injection before graph invocation in passthrough worker |
| `frameworks/langchain.py` | Same for LangChain passthrough worker |
| `__init__.py` | Export `resolve_credentials` helper |
| `AGENTS.md` | Document credential support for all tool types, external workers, thread safety |

### Java Server

| File | Change |
|------|--------|
| `CredentialAwareHttpTask.java` | NEW — extends `HttpTask`, resolves `${NAME}` in headers before execution |
| `JavaScriptBuilder.java` | Enrichment script passes `agentspanCtx` to HTTP and MCP task branches |
| `ToolCompiler.java` | Register `CredentialAwareHttpTask` as HTTP task handler |
| `AgentService.java` | Read `credentials` from workflow start input for token minting |

### Tests

| File | Change |
|------|--------|
| `tests/e2e/test_http_tool_credentials.py` | NEW — echo server + HTTP tool credential e2e |
| `tests/e2e/test_credential_e2e.py` | Extend with framework, extracted, external worker tests |
| `CredentialAwareHttpTaskTest.java` | NEW — `@SpringBootTest` with real credential store + HTTP call |
| `examples/17_http_tool_credentials.py` | NEW — real example demonstrating HTTP tool with credentials |

---

## What This Design Does NOT Cover

- **Credential caching** — every resolve call hits the DB. Can add per-workflow caching later.
- **Credential rotation** — changing a credential mid-workflow requires re-storing it. No hot-reload.
- **Vault/KMS backends** — `CredentialStoreProvider` interface supports pluggable backends (enterprise boundary).
- **Conductor `@worker_task` credential support** — deferred to core Python SDK work.
- **Multi-threaded passthrough workers** — documented as unsupported with credentials. `thread_count=1` enforced.
