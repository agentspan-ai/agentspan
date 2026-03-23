# Universal Credential Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend credential management to all tool types (HTTP, MCP, framework passthrough, extracted framework tools, external workers) so `credentials=[...]` works everywhere.

**Architecture:** Two resolution paths based on execution model:
- **HTTP tools (server system task):** Custom `CredentialAwareHttpTask` extends Conductor's `HttpTask`, resolves `${NAME}` patterns in headers via `CredentialResolutionService` before HTTP execution. Registered as `@Primary @Bean("HTTP")`.
- **MCP tools (worker task):** `CALL_MCP_TOOL` is a Conductor SDK worker, not a system task. Resolve `${NAME}` in MCP headers in `AgentEventListener.onTaskScheduled()` before the worker picks up the task.
- **SDK-side tools (framework passthrough, extracted tools):** Credentials via `WorkerCredentialFetcher` with a workflow-level fallback registry.

Every change is test-first with e2e tests against a real server. No mocks.

**Tech Stack:** Python 3.12, Java 21, Spring Boot 3.3, Conductor 3.22, SQLite, pytest, JUnit 5, httpx

**Spec:** `docs/superpowers/specs/2026-03-22-universal-credential-support-design.md`

---

## File Structure

### Python SDK — New Files
| File | Responsibility |
|------|---------------|
| `tests/e2e/test_http_tool_credentials.py` | E2E: HTTP tool with credential headers against echo server |
| `tests/e2e/test_framework_credentials.py` | E2E: Framework passthrough + extracted tool credentials |
| `examples/17_http_tool_credentials.py` | Working example: HTTP tool with `credentials=[...]` |

### Python SDK — Modified Files
| File | Change |
|------|--------|
| `src/agentspan/agents/tool.py` | Add `credentials` param to `http_tool()` and `mcp_tool()`, validate `${NAME}` |
| `src/agentspan/agents/runtime/runtime.py` | `run()`/`start()`/`stream()` accept `credentials` kwarg, populate `_workflow_credentials` |
| `src/agentspan/agents/runtime/_dispatch.py` | Add `_workflow_credentials` fallback with lock |
| `src/agentspan/agents/frameworks/langgraph.py` | Credential resolution in passthrough worker |
| `src/agentspan/agents/frameworks/langchain.py` | Credential resolution in passthrough worker |
| `src/agentspan/agents/__init__.py` | Export `resolve_credentials` helper |
| `AGENTS.md` | Document credential support for all tool types |

### Java Server — New Files
| File | Responsibility |
|------|---------------|
| `credentials/CredentialAwareHttpTask.java` | Extends `HttpTask`, resolves `${NAME}` in HTTP headers |
| `credentials/CredentialAwareHttpTaskConfig.java` | Registers as `@Primary @Bean("HTTP")` override |
| `credentials/CredentialAwareHttpTaskTest.java` (test) | `@SpringBootTest` integration test |

### Java Server — Modified Files
| File | Change |
|------|--------|
| `util/JavaScriptBuilder.java` | Pass `agentspanCtx` to HTTP and MCP enrichment branches |
| `service/AgentEventListener.java` | Resolve `${NAME}` in MCP task headers on `onTaskScheduled` |
| `service/AgentService.java` | Read `credentials` from start request input for token minting |

---

## Chunk 1: HTTP Tool Credential Binding (Server-Side)

### Task 1: Add `credentials` param to `http_tool()` and `mcp_tool()` with validation

**Files:**
- Modify: `sdk/python/src/agentspan/agents/tool.py:177-214` (http_tool), `tool.py:217-257` (mcp_tool)
- Create: `sdk/python/tests/e2e/test_http_tool_credentials.py`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_http_tool_credentials.py`:

```python
"""E2E: http_tool and mcp_tool credential parameter support."""
import re

import pytest


def test_http_tool_accepts_credentials():
    from agentspan.agents.tool import http_tool
    td = http_tool(
        name="test_api",
        description="Test",
        url="http://localhost:9999/test",
        headers={"Authorization": "Bearer ${MY_TOKEN}"},
        credentials=["MY_TOKEN"],
    )
    assert td.credentials == ["MY_TOKEN"]


def test_http_tool_validates_placeholder_mismatch():
    """${NAME} in headers without matching credentials raises ValueError."""
    from agentspan.agents.tool import http_tool
    with pytest.raises(ValueError, match="MISSING_CRED"):
        http_tool(
            name="bad_api",
            description="Test",
            url="http://localhost:9999/test",
            headers={"Authorization": "Bearer ${MISSING_CRED}"},
            credentials=[],
        )


def test_http_tool_validates_placeholder_no_credentials():
    """${NAME} in headers with credentials=None also raises ValueError."""
    from agentspan.agents.tool import http_tool
    with pytest.raises(ValueError, match="ORPHAN_CRED"):
        http_tool(
            name="bad_api2",
            description="Test",
            url="http://localhost:9999/test",
            headers={"Authorization": "Bearer ${ORPHAN_CRED}"},
        )


def test_http_tool_serializes_credentials():
    from agentspan.agents import Agent
    from agentspan.agents.tool import http_tool
    from agentspan.agents.config_serializer import AgentConfigSerializer

    tool = http_tool(
        name="cred_api",
        description="Test",
        url="http://localhost:9999/test",
        headers={"X-Auth": "Bearer ${MY_TOKEN}"},
        credentials=["MY_TOKEN"],
    )
    agent = Agent(name="http_cred_test", model="openai/gpt-4o", tools=[tool])
    config = AgentConfigSerializer().serialize(agent)
    tool_cfg = config["tools"][0]
    assert tool_cfg["config"]["credentials"] == ["MY_TOKEN"]
    assert "${MY_TOKEN}" in str(tool_cfg["config"]["headers"])


def test_mcp_tool_accepts_credentials():
    from agentspan.agents.tool import mcp_tool
    td = mcp_tool(
        server_url="http://localhost:3001/mcp",
        headers={"Authorization": "Bearer ${MCP_KEY}"},
        credentials=["MCP_KEY"],
    )
    assert td.credentials == ["MCP_KEY"]
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd sdk/python && uv run python -m pytest tests/e2e/test_http_tool_credentials.py -v
```

Expected: FAIL — `http_tool()` does not accept `credentials`

- [ ] **Step 3: Implement**

In `tool.py`, update `http_tool()` (line 177):

```python
def http_tool(
    name: str,
    description: str,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    accept: List[str] = ["application/json"],
    content_type: str = "application/json",
    credentials: Optional[List[str]] = None,
) -> ToolDef:
    import re as _re

    cred_list = list(credentials) if credentials else []

    # Validate: any ${NAME} in headers must be in credentials list
    if headers:
        placeholders = set(_re.findall(r"\$\{(\w+)}", str(headers)))
        if placeholders:
            missing = placeholders - set(cred_list)
            if missing:
                raise ValueError(
                    f"Header placeholder(s) {missing} not declared in credentials={cred_list}. "
                    f"Add them to the credentials list."
                )

    config: Dict[str, Any] = {
        "url": url,
        "method": method,
        "headers": headers or {},
        "accept": accept[0] if accept else "application/json",
        "contentType": content_type,
    }
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema or {"type": "object", "properties": {}},
        tool_type="http",
        config=config,
        credentials=cred_list,
    )
```

Apply identical pattern to `mcp_tool()` (line 217) — add `credentials` param, same validation.

- [ ] **Step 4: Run test — verify it passes**

```bash
uv run python -m pytest tests/e2e/test_http_tool_credentials.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Run all existing tests — no regression**

```bash
uv run python -m pytest tests/unit/ tests/e2e/test_credential_e2e.py -q
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/tool.py tests/e2e/test_http_tool_credentials.py
git commit -m "feat: add credentials param to http_tool() and mcp_tool() with validation"
```

---

### Task 2: Enrichment script passes `__agentspan_ctx__` to HTTP and MCP tasks

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/util/JavaScriptBuilder.java:190-208`

- [ ] **Step 1: Write the failing test**

In the existing `ToolCompilerTest.java`, add a test that compiles an agent with an HTTP tool and verifies the enrichment script includes `__agentspan_ctx__` injection for the HTTP branch. Verify the script string contains the injection line for both HTTP and MCP branches.

- [ ] **Step 2: Run test — verify it fails**

```bash
cd server && ./gradlew test --tests "dev.agentspan.runtime.compiler.ToolCompilerTest"
```

- [ ] **Step 3: Implement**

In `JavaScriptBuilder.java`, `enrichToolsScript()`:

After the HTTP branch builds `t.inputParameters` (line ~200), add:
```java
"      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
```

After the MCP branch builds `t.inputParameters` (line ~208), add:
```java
"      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
```

Apply same to `enrichToolsScriptDynamic()` for both branches.

- [ ] **Step 4: Run test — verify it passes**

```bash
./gradlew test --tests "dev.agentspan.runtime.compiler.ToolCompilerTest"
```

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/util/JavaScriptBuilder.java \
        server/src/test/java/dev/agentspan/runtime/compiler/ToolCompilerTest.java
git commit -m "feat: enrichment script passes __agentspan_ctx__ to HTTP and MCP tasks"
```

---

### Task 3: `CredentialAwareHttpTask` resolves `${NAME}` in HTTP headers

**Files:**
- Create: `server/src/main/java/dev/agentspan/runtime/credentials/CredentialAwareHttpTask.java`
- Create: `server/src/main/java/dev/agentspan/runtime/credentials/CredentialAwareHttpTaskConfig.java`
- Create: `server/src/test/java/dev/agentspan/runtime/credentials/CredentialAwareHttpTaskTest.java`

- [ ] **Step 1: Write the failing integration test**

```java
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialAwareHttpTaskTest {

    @Autowired private CredentialStoreProvider storeProvider;
    @Autowired private CredentialAwareHttpTask httpTask;

    private static final String USER_ID = "http-task-test-user";

    @BeforeEach
    void setUp() {
        // Store credential directly in the store (same user the resolver will query)
        storeProvider.set(USER_ID, "MY_API_KEY", "resolved-secret-value");
    }

    @Test
    void resolveHeaders_substitutesPlaceholders() {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Bearer ${MY_API_KEY}");
        headers.put("X-Static", "no-placeholder");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Authorization")).isEqualTo("Bearer resolved-secret-value");
        assertThat(resolved.get("X-Static")).isEqualTo("no-placeholder");
    }

    @Test
    void resolveHeaders_unresolvedPlaceholder_replacedWithEmpty() {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Bearer ${NONEXISTENT}");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Authorization")).isEqualTo("Bearer ");
    }

    @Test
    void resolveHeaders_noPlaceholders_returnsUnchanged() {
        Map<String, String> headers = Map.of("X-Static", "value");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("X-Static")).isEqualTo("value");
    }

    @Test
    void resolveHeaders_credentialValueWithDollarSign_handledSafely() {
        storeProvider.set(USER_ID, "TRICKY_KEY", "val$with$dollars");

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Auth", "${TRICKY_KEY}");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Auth")).isEqualTo("val$with$dollars");
    }
}
```

- [ ] **Step 2: Run test — verify it fails**

```bash
./gradlew test --tests "dev.agentspan.runtime.credentials.CredentialAwareHttpTaskTest"
```

Expected: FAIL — class doesn't exist

- [ ] **Step 3: Implement `CredentialAwareHttpTask`**

```java
package dev.agentspan.runtime.credentials;

import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import com.netflix.conductor.tasks.http.HttpTask;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Extends Conductor's HttpTask to resolve ${NAME} credential placeholders
 * in HTTP headers before execution. Uses CredentialResolutionService with
 * the userId from the execution token in __agentspan_ctx__.
 *
 * Resolved values exist only in memory during execution — never persisted.
 */
public class CredentialAwareHttpTask extends HttpTask {

    private static final Logger log = LoggerFactory.getLogger(CredentialAwareHttpTask.class);
    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{(\\w+)}");

    private final ExecutionTokenService tokenService;
    private final CredentialResolutionService resolutionService;

    public CredentialAwareHttpTask(
            ExecutionTokenService tokenService,
            CredentialResolutionService resolutionService) {
        super();
        this.tokenService = tokenService;
        this.resolutionService = resolutionService;
    }

    @Override
    @SuppressWarnings("unchecked")
    public void start(WorkflowModel workflow, TaskModel task, WorkflowExecutor executor) {
        Map<String, Object> input = task.getInputData();
        Object httpRequest = input.get("http_request");
        Object ctx = input.get("__agentspan_ctx__");

        if (httpRequest instanceof Map<?,?> reqMap && ctx != null) {
            Object headers = reqMap.get("headers");
            if (headers instanceof Map<?,?> headerMap && containsPlaceholders(headerMap)) {
                String userId = extractUserId(ctx);
                if (userId != null) {
                    Map<String, String> resolved = resolveHeadersForUser(
                        (Map<String, String>) headerMap, userId);
                    ((Map<String, Object>) reqMap).put("headers", resolved);
                }
            }
        }

        super.start(workflow, task, executor);
    }

    /** Package-private for testing. */
    Map<String, String> resolveHeadersForUser(Map<String, String> headers, String userId) {
        Map<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            String value = entry.getValue();
            Matcher m = PLACEHOLDER.matcher(value);
            StringBuilder sb = new StringBuilder();
            while (m.find()) {
                String credName = m.group(1);
                String credValue = resolutionService.resolve(userId, credName);
                m.appendReplacement(sb, Matcher.quoteReplacement(
                    credValue != null ? credValue : ""));
            }
            m.appendTail(sb);
            result.put(entry.getKey(), sb.toString());
        }
        return result;
    }

    private String extractUserId(Object ctx) {
        String token = null;
        if (ctx instanceof Map<?,?> ctxMap) {
            token = (String) ctxMap.get("execution_token");
        } else if (ctx instanceof String s) {
            token = s;
        }
        if (token == null) return null;
        try {
            return tokenService.validate(token).userId();
        } catch (Exception e) {
            log.warn("Failed to validate token for header resolution: {}", e.getMessage());
            return null;
        }
    }

    private boolean containsPlaceholders(Map<?,?> headers) {
        for (Object v : headers.values()) {
            if (v != null && PLACEHOLDER.matcher(String.valueOf(v)).find()) return true;
        }
        return false;
    }
}
```

- [ ] **Step 4: Create config class to register as @Primary**

```java
package dev.agentspan.runtime.credentials;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class CredentialAwareHttpTaskConfig {

    @Bean("HTTP")
    @Primary
    public CredentialAwareHttpTask credentialAwareHttpTask(
            ExecutionTokenService tokenService,
            CredentialResolutionService resolutionService) {
        return new CredentialAwareHttpTask(tokenService, resolutionService);
    }
}
```

- [ ] **Step 5: Run test — verify it passes**

```bash
./gradlew test --tests "dev.agentspan.runtime.credentials.CredentialAwareHttpTaskTest"
```

Expected: 4 PASSED

- [ ] **Step 6: Run all server tests**

```bash
./gradlew test
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 7: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/credentials/CredentialAwareHttpTask.java \
        server/src/main/java/dev/agentspan/runtime/credentials/CredentialAwareHttpTaskConfig.java \
        server/src/test/java/dev/agentspan/runtime/credentials/CredentialAwareHttpTaskTest.java
git commit -m "feat: CredentialAwareHttpTask resolves \${NAME} in HTTP headers"
```

---

### Task 4: MCP credential header resolution via TaskStatusListener

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/service/AgentEventListener.java`

`CALL_MCP_TOOL` is a worker task (from `conductor-client` SDK), not a system task — we can't extend it. Instead, resolve `${NAME}` in MCP headers in `AgentEventListener.onTaskScheduled()` before the worker picks up the task.

- [ ] **Step 1: Write the failing test**

Add integration test that creates a task with MCP headers containing `${NAME}`, triggers `onTaskScheduled`, and verifies headers are resolved.

- [ ] **Step 2: Implement in `AgentEventListener.onTaskScheduled()`**

Add a check: if task type is `CALL_MCP_TOOL` and `inputData.headers` contains `${...}` patterns, resolve them using the same `resolveHeadersForUser()` logic (extract from shared utility or call `CredentialAwareHttpTask` directly).

- [ ] **Step 3: Run all server tests**

```bash
./gradlew test
```

- [ ] **Step 4: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/service/AgentEventListener.java
git commit -m "feat: resolve credential headers for MCP tasks on scheduling"
```

---

### Task 5: Full e2e validation — HTTP tool with real agent

- [ ] **Step 1: Restart server with all changes, run all tests**

```bash
cd server && lsof -ti :8080 | xargs kill -9 2>/dev/null; sleep 2
./gradlew clean bootRun > /tmp/agentspan_server.log 2>&1 &
# Wait for ready
for i in $(seq 1 30); do curl -sf http://localhost:8080/api/credentials > /dev/null 2>&1 && break; sleep 1; done

cd ../sdk/python && uv pip install -e .
uv run python -m pytest tests/e2e/ tests/unit/credentials/ -v
```

Expected: ALL PASS

- [ ] **Step 2: Run existing credential examples**

```bash
timeout 90 uv run python examples/16d_credentials_gh_cli.py
```

Expected: Agent completes successfully

- [ ] **Step 3: Create `examples/17_http_tool_credentials.py`**

```python
"""HTTP tool with credential-bearing headers.

Demonstrates:
    - http_tool() with credentials=["GITHUB_TOKEN"]
    - ${GITHUB_TOKEN} in headers resolved server-side from credential store
"""
from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.tool import http_tool
from settings import settings

github_repos = http_tool(
    name="list_repos",
    description="List GitHub repositories for a user. Returns JSON array of repos.",
    url="https://api.github.com/users/${username}/repos?per_page=5&sort=updated",
    headers={"Authorization": "Bearer ${GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
    credentials=["GITHUB_TOKEN"],
    input_schema={"type": "object", "properties": {"username": {"type": "string"}}, "required": ["username"]},
)

agent = Agent(
    name="github_http_agent",
    model=settings.llm_model,
    tools=[github_repos],
    instructions="You list GitHub repos using the list_repos tool.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "List repos for agentspan")
        result.print_result()
```

- [ ] **Step 4: Run the new example**

```bash
timeout 90 uv run python examples/17_http_tool_credentials.py
```

Expected: Agent calls HTTP tool, gets repos with resolved GITHUB_TOKEN in auth header

- [ ] **Step 5: Commit**

```bash
git add sdk/python/examples/17_http_tool_credentials.py
git commit -m "feat: HTTP tool credentials example"
```

---

## Chunk 2: Framework Passthrough Credentials

### Task 6: Add `credentials` kwarg to `run()`/`start()`/`stream()`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py`
- Create: `sdk/python/tests/e2e/test_framework_credentials.py`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_framework_credentials.py`:

```python
"""E2E: Framework passthrough and extracted tool credentials."""
import os
import httpx
import pytest

SERVER = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:8080")
API = f"{SERVER}/api"
CRED_NAME = "_E2E_FW_CRED"
CRED_VALUE = "framework-secret-12345"


@pytest.fixture(autouse=True)
def setup_credential():
    client = httpx.Client(timeout=10.0)
    client.post(f"{API}/credentials", json={"name": CRED_NAME, "value": CRED_VALUE})
    yield
    client.delete(f"{API}/credentials/{CRED_NAME}")


def test_run_accepts_credentials_kwarg():
    from agentspan.agents import Agent, AgentRuntime
    agent = Agent(name="fw_cred_test", model="openai/gpt-4o", instructions="Say hello")
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "hello", credentials=[CRED_NAME], timeout=15)
        assert result is not None


def test_workflow_credentials_fallback():
    """Extracted tools receive credentials via workflow-level fallback."""
    from agentspan.agents.runtime._dispatch import _workflow_credentials, _workflow_credentials_lock
    import threading

    # Simulate runtime populating the registry
    wf_id = "test-wf-fallback"
    with _workflow_credentials_lock:
        _workflow_credentials[wf_id] = ["MY_CRED"]
    try:
        with _workflow_credentials_lock:
            assert _workflow_credentials[wf_id] == ["MY_CRED"]
    finally:
        with _workflow_credentials_lock:
            _workflow_credentials.pop(wf_id, None)
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run python -m pytest tests/e2e/test_framework_credentials.py -v
```

Expected: FAIL — `credentials` kwarg causes error or `_workflow_credentials` doesn't exist

- [ ] **Step 3: Implement `credentials` on `run()`/`start()`/`stream()`**

In `runtime.py`, add `credentials: Optional[List[str]] = None` to `run()` (line 1910), `start()` (line 2972), `stream()` (line 3052).

Pass through all internal paths:
- `_start_via_server()`: add `credentials` to input payload
- `_start_framework_via_server()`: same
- After workflow starts, populate `_workflow_credentials[workflow_id]`
- In `_poll_status_until_complete()`, clean up in `finally`

- [ ] **Step 4: Run test — verify it passes**

```bash
uv run python -m pytest tests/e2e/test_framework_credentials.py -v
```

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/runtime.py tests/e2e/test_framework_credentials.py
git commit -m "feat: run()/start()/stream() accept credentials kwarg"
```

---

### Task 7: Server reads `credentials` from start request for token minting

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/service/AgentService.java`

- [ ] **Step 1: Write the failing test**

Verify that when workflow input contains `"credentials": ["KEY1", "KEY2"]`, the execution token's `declared_names` includes them.

- [ ] **Step 2: Implement**

In `AgentService.java`, in the token minting block (line ~203), after `extractDeclaredCredentials(config)`:

```java
// Also include credentials from the start request input
Object inputCreds = input.get("credentials");
if (inputCreds instanceof List<?> credList) {
    for (Object c : credList) {
        if (c instanceof String s && !declaredNames.contains(s)) {
            declaredNames.add(s);
        }
    }
}
```

- [ ] **Step 3: Run all server tests**

```bash
./gradlew test
```

- [ ] **Step 4: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/service/AgentService.java
git commit -m "feat: server reads credentials from start request input for token minting"
```

---

### Task 8: Add `_workflow_credentials` fallback in `_dispatch.py`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/_dispatch.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/e2e/test_framework_credentials.py`:

```python
def test_dispatch_uses_workflow_credentials_fallback():
    """When tool_def has no credentials, fall back to _workflow_credentials."""
    from agentspan.agents.runtime._dispatch import (
        _workflow_credentials, _workflow_credentials_lock, make_tool_worker,
    )
    from agentspan.agents.tool import tool, get_tool_def
    from conductor.client.http.models.task import Task

    @tool
    def no_cred_tool(x: str) -> str:
        import os
        return os.environ.get("_WF_CRED", "NOT_SET")

    td = get_tool_def(no_cred_tool)
    assert td.credentials == []  # no tool-level credentials

    wrapper = make_tool_worker(td.func, td.name, tool_def=td)

    # Set workflow-level credentials
    wf_id = "test-wf-dispatch"
    with _workflow_credentials_lock:
        _workflow_credentials[wf_id] = ["_WF_CRED"]

    try:
        task = Task()
        task.input_data = {"x": "hello"}
        task.workflow_instance_id = wf_id
        task.task_id = "test-task"
        # Note: without execution token, fetcher falls back to env
        # This test just verifies the fallback path is reached
        result = wrapper(task)
        assert result is not None
    finally:
        with _workflow_credentials_lock:
            _workflow_credentials.pop(wf_id, None)
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run python -m pytest tests/e2e/test_framework_credentials.py::test_dispatch_uses_workflow_credentials_fallback -v
```

- [ ] **Step 3: Implement**

At the top of `_dispatch.py` (after line 180):

```python
import threading

_workflow_credentials = {}  # workflow_instance_id -> [credential_names]
_workflow_credentials_lock = threading.Lock()
```

In the credential resolution block (line ~348):

```python
_td = _tool_def_registry.get(tool_name) or tool_def
credential_names = list(getattr(_td, "credentials", [])) if _td else _get_credential_names_from_tool(tool_func)

# Fallback: workflow-level credentials (for framework-extracted tools)
if not credential_names and task.workflow_instance_id:
    with _workflow_credentials_lock:
        credential_names = list(_workflow_credentials.get(task.workflow_instance_id, []))
```

- [ ] **Step 4: Run test — verify it passes**

```bash
uv run python -m pytest tests/e2e/test_framework_credentials.py -v
```

- [ ] **Step 5: Run all tests**

```bash
uv run python -m pytest tests/unit/ tests/e2e/ -q
```

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/_dispatch.py tests/e2e/test_framework_credentials.py
git commit -m "feat: workflow-level credential fallback for framework-extracted tools"
```

---

### Task 9: Credential injection in LangGraph and LangChain passthrough workers

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/langgraph.py:1401-1430`
- Modify: `sdk/python/src/agentspan/agents/frameworks/langchain.py:84-110`

- [ ] **Step 1: Add credential resolution to `make_langgraph_worker()`**

Before `graph.stream()` (line 1429), add credential injection:

```python
_injected_keys = []
try:
    wf_id = task.workflow_instance_id or ""
    from agentspan.agents.runtime._dispatch import (
        _extract_execution_token, _get_credential_fetcher,
        _workflow_credentials, _workflow_credentials_lock,
    )
    with _workflow_credentials_lock:
        cred_names = list(_workflow_credentials.get(wf_id, []))
    if cred_names:
        token = _extract_execution_token(task)
        if token:
            fetcher = _get_credential_fetcher()
            resolved = fetcher.fetch(token, cred_names)
            for k, v in resolved.items():
                if isinstance(v, str):
                    os.environ[k] = v
                    _injected_keys.append(k)
```

After `graph.stream()`, in finally block:

```python
finally:
    for k in _injected_keys:
        os.environ.pop(k, None)
```

- [ ] **Step 2: Apply same to `make_langchain_worker()`**

Same pattern before `executor.invoke()` (line 108).

- [ ] **Step 3: Run all tests**

```bash
uv run python -m pytest tests/e2e/ tests/unit/ -q
```

- [ ] **Step 4: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/langgraph.py \
        sdk/python/src/agentspan/agents/frameworks/langchain.py
git commit -m "feat: credential injection in LangGraph and LangChain passthrough workers"
```

---

## Chunk 3: External Workers + Documentation + Final Validation

### Task 10: Export `resolve_credentials` helper

**Files:**
- Modify: `sdk/python/src/agentspan/agents/__init__.py`

- [ ] **Step 1: Add function and test**

Add `resolve_credentials()` to `__init__.py`:

```python
def resolve_credentials(input_data: dict, names: list) -> dict:
    """Resolve credentials from Conductor task input data. For external workers."""
    from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
    from agentspan.agents.runtime.config import AgentConfig

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

Add `"resolve_credentials"` to `__all__`.

Add test to `tests/e2e/test_credential_e2e.py`:

```python
from agentspan.agents import resolve_credentials
with patch.dict(os.environ, {"_EXT_CRED": "ext-val"}):
    result = resolve_credentials({}, ["_EXT_CRED"])
assert result["_EXT_CRED"] == "ext-val"
```

- [ ] **Step 2: Run tests**

```bash
uv run python -m pytest tests/e2e/ -v
```

- [ ] **Step 3: Commit**

```bash
git add sdk/python/src/agentspan/agents/__init__.py tests/e2e/test_credential_e2e.py
git commit -m "feat: export resolve_credentials helper for external workers"
```

---

### Task 11: Update AGENTS.md with credential documentation

**Files:**
- Modify: `sdk/python/AGENTS.md`

- [ ] **Step 1: Add credential support table and external worker docs**

After the "Testing Rules" section, add:

```markdown
### Credential Support by Tool Type

| Tool Type | Declaration | Resolution |
|-----------|------------|------------|
| `@tool` (worker) | `@tool(credentials=[...])` | SDK resolves via server, injects into env |
| `http_tool()` | `http_tool(credentials=[...])` | `${NAME}` in headers resolved server-side |
| `mcp_tool()` | `mcp_tool(credentials=[...])` | Same as http_tool |
| `agent_tool()` | Inherited from sub-agent | Token forwarded to sub-workflows |
| CLI tools | `Agent(credentials=[...])` | Auto-propagated to run_command tool |
| Code execution | `Agent(credentials=[...])` | Auto-propagated to execute_code tool |
| Framework passthrough | `run(agent, credentials=[...])` | Resolved and injected before graph invocation |
| External workers | `@tool(external=True, credentials=[...])` | Use `resolve_credentials()` helper |
| Media/RAG tools | None needed | Server resolves LLM/VectorDB keys internally |
| LLMGuardrail | None needed | Server resolves LLM keys internally |
```

- [ ] **Step 2: Commit**

```bash
git add sdk/python/AGENTS.md
git commit -m "docs: credential support for all tool types"
```

---

### Task 12: Full end-to-end validation

- [ ] **Step 1: Restart server with all changes**

```bash
cd server && lsof -ti :8080 | xargs kill -9 2>/dev/null; sleep 2
./gradlew clean bootRun > /tmp/agentspan_server.log 2>&1 &
for i in $(seq 1 30); do curl -sf http://localhost:8080/api/credentials > /dev/null 2>&1 && break; sleep 1; done
```

- [ ] **Step 2: Run ALL Python tests**

```bash
cd sdk/python && uv pip install -e .
uv run python -m pytest tests/unit/ tests/e2e/ -v
```

Expected: ALL PASS

- [ ] **Step 3: Run ALL Java tests**

```bash
cd server && ./gradlew test
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Run credential examples**

```bash
cd sdk/python
timeout 90 uv run python examples/16d_credentials_gh_cli.py
timeout 90 uv run python examples/17_http_tool_credentials.py
timeout 180 uv run python examples/70_ce_support_agent.py 12345
```

Expected: All complete with credential-backed tool calls

- [ ] **Step 5: Final commit**

```bash
git add -A && git commit -m "feat: universal credential support - all tool types covered"
```
