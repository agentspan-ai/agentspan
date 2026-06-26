# Pipeline Context Passing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pass structured state (repo paths, branch names, working directories) between pipeline steps and swarm handoffs via a `context` dict, so agents don't have to parse LLM prose to find concrete values.

**Architecture:** The context dict flows through Conductor SUB_WORKFLOW input/output parameters. Tools write to `ToolContext.state` (already exists), which persists as `_agent_state` within DO_WHILE loops. At sub-workflow boundaries, `_agent_state` is emitted as `output.context` and the next sub-workflow initializes `_agent_state` from `input.context`. The context is injected as a JSON block prepended to the LLM's user message.

**Tech Stack:** Java (server compiler), Python SDK, TypeScript SDK, Conductor workflow JSON, GraalJS inline tasks.

**Spec:** `docs/superpowers/specs/2026-04-01-pipeline-context-passing-design.md`

---

## File Structure

### Server (Java)
| File | Action | Responsibility |
|------|--------|---------------|
| `server/.../compiler/AgentCompiler.java` | Modify | Init `_agent_state` from `input.context`, add `context` to all `setOutputParameters`, add context to `compileSubAgent` input, prepend context to LLM user message |
| `server/.../compiler/MultiAgentCompiler.java` | Modify | Sequential: init + merge + thread context. Parallel: namespaced merge. Swarm/rotation/handoff/manual/router: shared context in SET_VARIABLE |
| `server/src/test/.../compiler/ContextPassingTest.java` | Create | Compiler unit tests for context wiring |

### Python SDK
| File | Action | Responsibility |
|------|--------|---------------|
| `sdk/python/src/agentspan/agents/cli_config.py` | Modify | Add `context: ToolContext` + `context_key` to `run_command` |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | Modify | Add `context` param to `run()`, `start()`, `run_async()`, `start_async()`. Thread context into HTTP payload. |
| `sdk/python/tests/unit/test_cli_config.py` | Modify | Add `context_key` tests + negative tests |
| `sdk/python/tests/unit/test_context_passing.py` | Create | Context in HTTP payload, injection formatting, size limit tests |

### TypeScript SDK
| File | Action | Responsibility |
|------|--------|---------------|
| `sdk/typescript/src/cli-config.ts` | Modify | Add `context_key` to schema, read `__toolContext__` |
| `sdk/typescript/src/types.ts` | Modify | Add `context` to `RunOptions` |
| `sdk/typescript/src/runtime.ts` | Modify | Add `context` to payload in `run()`, `start()`, `stream()` |
| `sdk/typescript/tests/unit/cli-config.test.ts` | Modify | Add `context_key` tests + negative tests |
| `sdk/typescript/tests/unit/context-passing.test.ts` | Create | Context in payload, injection formatting, size limit tests |

---

## Chunk 1: SDK — `context_key` on CLI Tools (Python + TypeScript)

The CLI tool is the most common tool in the failed pipeline. This chunk makes `run_command` capable of writing to `ToolContext.state`.

### Task 1: Python CLI tool `context_key`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/cli_config.py:106-123`
- Modify: `sdk/python/tests/unit/test_cli_config.py`

- [ ] **Step 1: Write failing test for `context_key` on success**

```python
# In tests/unit/test_cli_config.py — add to TestMakeCliTool class

def test_context_key_saves_stdout_on_success(self):
    from agentspan.agents.tool import ToolContext
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/tmp/abc123\n", stderr=""
        )
        ctx = ToolContext(execution_id="test", agent_name="test", state={})
        result = tool_fn.__wrapped__(command="mktemp", args=["-d"], context_key="working_dir", context=ctx)
        assert result["status"] == "success"
        assert ctx.state["working_dir"] == "/tmp/abc123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_cli_config.py::TestMakeCliTool::test_context_key_saves_stdout_on_success -v`
Expected: FAIL (context parameter not accepted)

- [ ] **Step 3: Write failing test for `context_key` NOT saved on failure**

```python
def test_context_key_not_saved_on_failure(self):
    from agentspan.agents.tool import ToolContext
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="partial output", stderr="error"
        )
        ctx = ToolContext(execution_id="test", agent_name="test", state={})
        with pytest.raises(TerminalToolError):
            tool_fn.__wrapped__(command="false", context_key="result", context=ctx)
        assert "result" not in ctx.state
```

- [ ] **Step 4: Write negative test — `context_key` collision with internal key**

```python
def test_context_key_with_internal_key_name(self):
    """context_key='_agent_state' should work without corrupting internals."""
    from agentspan.agents.tool import ToolContext
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
        ctx = ToolContext(execution_id="test", agent_name="test", state={})
        result = tool_fn.__wrapped__(command="echo", args=["val"], context_key="_agent_state", context=ctx)
        assert result["status"] == "success"
        assert ctx.state["_agent_state"] == "val"

def test_context_key_empty_string_is_noop(self):
    """Empty context_key should not write anything."""
    from agentspan.agents.tool import ToolContext
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
        ctx = ToolContext(execution_id="test", agent_name="test", state={})
        tool_fn.__wrapped__(command="echo", context_key="", context=ctx)
        assert ctx.state == {}
```

- [ ] **Step 5: Implement — add `context` and `context_key` to `run_command`**

In `cli_config.py`, modify the `run_command` inner function signature to accept `context: ToolContext = None` and `context_key: str = ""`. After a successful command (returncode == 0), if `context_key` is non-empty and `context` is not None, write `context.state[context_key] = result.stdout.strip()`.

Update the tool description to mention `context_key` and well-known keys:
```
"If you need to save a command's output for later pipeline steps, set context_key.
Well-known keys: repo, branch, working_dir, issue_number, pr_url, commit_sha."
```

- [ ] **Step 6: Run all CLI config tests**

Run: `cd sdk/python && uv run pytest tests/unit/test_cli_config.py -v`
Expected: All pass including new tests

- [ ] **Step 7: Commit**

```bash
git add sdk/python/src/agentspan/agents/cli_config.py sdk/python/tests/unit/test_cli_config.py
git commit -m "feat(python): add context_key parameter to CLI run_command tool"
```

### Task 2: TypeScript CLI tool `context_key`

**Files:**
- Modify: `sdk/typescript/src/cli-config.ts:91-135`
- Modify: `sdk/typescript/tests/unit/cli-config.test.ts`

- [ ] **Step 1: Write failing test for `context_key` on success**

```typescript
// In tests/unit/cli-config.test.ts — add to describe block

it('writes stdout to toolContext.state when context_key is set', async () => {
  mockedExecSync.mockReturnValue('/tmp/abc123\n');
  const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
  const toolContext = { state: {} };
  const result = await tool.func!({
    command: 'mktemp', args: ['-d'],
    context_key: 'working_dir',
    __toolContext__: toolContext,
  });
  expect(result.status).toBe('success');
  expect(toolContext.state).toEqual({ working_dir: '/tmp/abc123' });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/typescript && npx vitest run tests/unit/cli-config.test.ts`
Expected: FAIL (context_key not handled)

- [ ] **Step 3: Write failing tests for failure + edge cases**

```typescript
it('does not write to toolContext.state on non-zero exit', async () => {
  const err = new Error('fail') as any;
  err.status = 1; err.stdout = 'out'; err.stderr = 'err';
  mockedExecSync.mockImplementation(() => { throw err; });
  const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
  const toolContext = { state: {} };
  await expect(tool.func!({
    command: 'false', context_key: 'result',
    __toolContext__: toolContext,
  })).rejects.toThrow(TerminalToolError);
  expect(toolContext.state).toEqual({});
});

it('empty context_key is a no-op', async () => {
  mockedExecSync.mockReturnValue('val\n');
  const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
  const toolContext = { state: {} };
  await tool.func!({ command: 'echo', context_key: '', __toolContext__: toolContext });
  expect(toolContext.state).toEqual({});
});

it('works without __toolContext__ (backward compat)', async () => {
  mockedExecSync.mockReturnValue('val\n');
  const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
  const result = await tool.func!({ command: 'echo', context_key: 'x' });
  expect(result.status).toBe('success');
  // No crash, context_key silently ignored
});
```

- [ ] **Step 4: Implement — add `context_key` handling to `makeCliTool`**

In `cli-config.ts`, inside the `func` handler:
1. Extract and delete `__toolContext__` from args before command processing
2. Extract and delete `context_key` from args before command processing
3. Add `context_key` to the input schema properties
4. On success, if `context_key` is non-empty and `__toolContext__` exists, write `toolContext.state[context_key] = output.trim()`
5. Update tool description to mention `context_key` and well-known keys

- [ ] **Step 5: Run all CLI config tests**

Run: `cd sdk/typescript && npx vitest run tests/unit/cli-config.test.ts`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add sdk/typescript/src/cli-config.ts sdk/typescript/tests/unit/cli-config.test.ts
git commit -m "feat(typescript): add context_key parameter to CLI run_command tool"
```

---

## Chunk 2: SDK — `context` Parameter on `run()` / `start()` / `stream()`

### Task 3: Python runtime accepts `context`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py:2161-2174, 3259-3268, 3600, 3764`
- Create: `sdk/python/tests/unit/test_context_passing.py`

**Note:** The Python `config_serializer.py` does NOT handle prompt or options — the runtime constructs the HTTP payload directly in `_run_native()` / `_start_native()`. Thread `context` through the runtime's payload construction, not the serializer.

- [ ] **Step 1: Write failing test — context appears in HTTP payload**

**Note:** `run()` accepts `**kwargs`, so passing `context=` won't TypeError — it'll be logged as "Unrecognized keyword arguments." The test must assert that context reaches the actual HTTP POST body, not just that the parameter is accepted.

```python
# tests/unit/test_context_passing.py
from unittest.mock import patch, MagicMock, ANY
from agentspan.agents import Agent

def test_run_includes_context_in_start_payload():
    """Verify context dict ends up in the /agent/start POST body."""
    agent = Agent(name="test", model="openai/gpt-4o-mini")
    # Mock the HTTP client's start_agent method to capture the payload
    with patch("agentspan.agents.runtime.http_client.HttpClient.start_agent") as mock_start:
        mock_start.return_value = {"executionId": "test-id", "requiredWorkers": []}
        from agentspan.agents import AgentRuntime
        rt = AgentRuntime()
        try:
            rt.run(agent, "hello", context={"repo": "test/repo"})
        except Exception:
            pass  # Will fail downstream (no SSE stream); we only check the payload
        mock_start.assert_called_once()
        payload = mock_start.call_args[0][0]  # first positional arg
        assert "context" in payload
        assert payload["context"] == {"repo": "test/repo"}

def test_run_without_context_omits_key():
    """Without context param, payload should not include context key."""
    agent = Agent(name="test", model="openai/gpt-4o-mini")
    with patch("agentspan.agents.runtime.http_client.HttpClient.start_agent") as mock_start:
        mock_start.return_value = {"executionId": "test-id", "requiredWorkers": []}
        from agentspan.agents import AgentRuntime
        rt = AgentRuntime()
        try:
            rt.run(agent, "hello")
        except Exception:
            pass
        payload = mock_start.call_args[0][0]
        assert "context" not in payload or payload.get("context") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_context_passing.py -v`
Expected: FAIL (context not in payload — currently swallowed by `**kwargs`)

- [ ] **Step 3: Implement — add `context` to all four methods**

In `runtime.py`, add `context: Optional[Dict[str, Any]] = None` to:
- `run()` (line 2161)
- `start()` (line 3259)
- `run_async()` (line 3600)
- `start_async()` (line 3764)

In the payload construction (inside `_run_native` or wherever the HTTP body is assembled), add:
```python
if context:
    payload["context"] = context
```

- [ ] **Step 4: Run tests**

Run: `cd sdk/python && uv run pytest tests/unit/test_context_passing.py -v`
Expected: PASS

- [ ] **Step 5: Run regression — quickstart harness**

Run: `cd sdk/python && uv run python examples/quickstart/run_all.py`
Expected: 4 passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/runtime.py sdk/python/tests/unit/test_context_passing.py
git commit -m "feat(python): add context parameter to run(), start(), run_async(), start_async()"
```

### Task 4: TypeScript runtime accepts `context`

**Files:**
- Modify: `sdk/typescript/src/types.ts:231-239`
- Modify: `sdk/typescript/src/runtime.ts:93-127, 182-220` (run, start, stream)
- Create: `sdk/typescript/tests/unit/context-passing.test.ts`

**Note:** In the TS runtime, `context` should be added to the `payload` object AFTER `serialize()` (same pattern as `timeoutSeconds` and `credentials` at lines 110-115), not inside `SerializeOptions`.

- [ ] **Step 1: Write failing test — context in RunOptions**

```typescript
// tests/unit/context-passing.test.ts
import { describe, it, expect } from 'vitest';

describe('RunOptions context', () => {
  it('accepts context in RunOptions type', () => {
    const options: import('../../src/types.js').RunOptions = {
      context: { repo: 'test/repo', branch: 'main' },
    };
    expect(options.context).toEqual({ repo: 'test/repo', branch: 'main' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/typescript && npx vitest run tests/unit/context-passing.test.ts`
Expected: FAIL (context not in RunOptions)

- [ ] **Step 3: Implement**

In `types.ts`, add to `RunOptions`:
```typescript
context?: Record<string, unknown>;
```

In `runtime.ts`, in `run()` (~line 110-115), `start()` (~line 197-200), and `stream()`, add after the existing payload modifications:
```typescript
if (options?.context) {
  payload.context = options.context;
}
```

- [ ] **Step 4: Run tests**

Run: `cd sdk/typescript && npx vitest run tests/unit/context-passing.test.ts`
Expected: PASS

- [ ] **Step 5: Run regression — quickstart harness**

Run: `cd sdk/typescript && npx tsx examples/quickstart/run-all.ts`
Expected: 4 passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add sdk/typescript/src/types.ts sdk/typescript/src/runtime.ts sdk/typescript/tests/unit/context-passing.test.ts
git commit -m "feat(typescript): add context parameter to run(), start(), stream()"
```

---

## Chunk 3: Server — Agent Loop Context Bridge + Tests

This is the core change: bridging `_agent_state` to `context` at sub-workflow boundaries. Each implementation step is paired with a compiler test.

### Task 5: Initialize `_agent_state` from `workflow.input.context` + test

**Files:**
- Modify: `server/.../compiler/AgentCompiler.java:444, 699`
- Create: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Write compiler test — agent loop initializes from input context**

```java
// ContextPassingTest.java
@Test
void agentLoop_initializesAgentStateFromInputContext() {
    // Compile a simple agent with tools
    // Assert: the SET_VARIABLE task for _agent_state references workflow.input.context
    // Assert: it does NOT hard-code an empty map
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: FAIL (still uses empty LinkedHashMap)

- [ ] **Step 3: Implement — change `_agent_state` initialization**

Conductor's SET_VARIABLE cannot evaluate null-coalescing expressions. Use the INLINE → SET_VARIABLE pattern:

1. Add an INLINE (GraalJS) task before the SET_VARIABLE that resolves context:
```java
// INLINE task: resolve input context with null fallback
// GraalJS: (function(){ return $.ctx || {}; })()
// Input: ctx -> ${workflow.input.context}
// Output: result -> the resolved context dict
```
2. SET_VARIABLE reads from the INLINE task's output:
```java
initVars.put("_agent_state", "${" + inlineTaskRef + ".output.result}");
```

Apply at both line 444 (in `compileWithTools()`) and line 699 (in `compileHybrid()`).

- [ ] **Step 4: Write compiler test — agent loop outputs context**

```java
@Test
void agentLoop_outputsContextFromAgentState() {
    // Compile a simple agent
    // Assert: setOutputParameters includes "context" key
    // Assert: context value references ${workflow.variables._agent_state}
}
```

- [ ] **Step 5: Implement — add `context` to all `setOutputParameters` calls**

For each output mapping (lines 157, 225, 497, 503, 729), add:
```java
outputParams.put("context", "${workflow.variables._agent_state}");
```

- [ ] **Step 6: Run tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): bridge _agent_state to context at sub-workflow boundaries"
```

### Task 6: Pass `context` in `compileSubAgent()` input + test

**Files:**
- Modify: `server/.../compiler/AgentCompiler.java:741-770`
- Modify: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Write compiler test — sub-workflow input includes context**

```java
@Test
void compileSubAgent_includesContextInSubWorkflowInput() {
    // Compile a 2-step sequential pipeline
    // Find the SUB_WORKFLOW tasks
    // Assert: each SUB_WORKFLOW input parameters include "context" key
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: FAIL (no context in sub-workflow input)

- [ ] **Step 3: Implement — add `contextRef` parameter to `compileSubAgent`**

Add `String contextRef` parameter to the method signature. Add `inputs.put("context", contextRef)` to the input map.

Update ALL **direct** callers of `compileSubAgent` — this is the blast radius:
- `MultiAgentCompiler.compileSequential()` (x2) — passes `${workflow.variables.context}`
- `MultiAgentCompiler.compileParallel()` — passes `${workflow.variables.context}`
- `MultiAgentCompiler.buildRotationCaseTasks()` — passes `${workflow.variables._agent_state}`
- `MultiAgentCompiler.buildHandoffCaseTasks()` — passes `${workflow.variables._agent_state}` (serves both router and handoff strategies)

**NOT via `compileSubAgent`** (separate handling needed in Task 10):
- `MultiAgentCompiler.buildSwarmCaseTasks()` — builds SUB_WORKFLOW manually (does NOT call `compileSubAgent`). Add `subInputs.put("context", "${workflow.variables._agent_state}")` directly at line ~1273.

- [ ] **Step 4: Run tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 5: Run full server test suite**

Run: `cd server && ./gradlew test`
Expected: All pass (no regressions from signature change)

- [ ] **Step 6: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java server/src/main/java/dev/agentspan/runtime/compiler/MultiAgentCompiler.java server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): pass context to sub-workflow inputs via compileSubAgent"
```

### Task 7: LLM message injection — prepend context to user message + test

**Files:**
- Modify: `server/.../compiler/AgentCompiler.java` (LLM task input assembly)
- Modify: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Write compiler test — INLINE context injection task exists before LLM task**

```java
@Test
void agentLoop_prependsContextToUserMessage() {
    // Compile an agent with tools
    // Find the LLM_CHAT_COMPLETE task
    // Assert: an INLINE task precedes it that formats context as JSON block
    // Assert: the LLM task reads its prompt from the INLINE task's output
}
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement — add INLINE GraalJS task for context injection**

Add an INLINE task before LLM_CHAT_COMPLETE that:
1. Reads `_agent_state` from workflow variables
2. If non-empty: `"Context:\n```json\n" + JSON.stringify(state, null, 2) + "\n```\n\n" + prompt`
3. If empty: passes prompt unchanged
4. The LLM task reads from this task's output

- [ ] **Step 4: Run tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): prepend context JSON to LLM user message"
```

---

## Chunk 4: Server — Multi-Agent Strategy Context Wiring + Tests

### Task 8: Sequential pipeline — context init, merge, thread + test

**Files:**
- Modify: `server/.../compiler/MultiAgentCompiler.java:232-304`
- Modify: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Write compiler test**

```java
@Test
void sequential_initializesMergesAndThreadsContext() {
    // Compile a 2-step sequential pipeline
    // Assert: SET_VARIABLE for context init at start
    // Assert: INLINE merge task between steps
    // Assert: pipeline output includes context
}
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement**

In `compileSequential()`:
1. Add INLINE task to resolve `workflow.input.context` with null fallback to `{}` (same INLINE → SET_VARIABLE pattern as Task 5 — Conductor SET_VARIABLE cannot null-coalesce). Task ref: `config.getName() + "_ctx_init_resolve"` for INLINE, `config.getName() + "_ctx_init"` for SET_VARIABLE.
2. After each SUB_WORKFLOW, add INLINE flat-merge (`config.getName() + "_ctx_merge_" + i`) + SET_VARIABLE (`config.getName() + "_ctx_set_" + i`) to persist merged context.
3. Pipeline output includes `context: ${workflow.variables.context}`

**Gated pipelines:** No special handling — merge tasks only run for completed steps. The accumulated context at gate termination is the final output.

- [ ] **Step 4: Run tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/MultiAgentCompiler.java server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): sequential pipeline context init, merge, and threading"
```

### Task 9: Parallel — namespaced context merge after JOIN + test

**Files:**
- Modify: `server/.../compiler/MultiAgentCompiler.java:401-450`
- Modify: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Write compiler test**

```java
@Test
void parallel_namespacedContextMergeAfterJoin() {
    // Compile parallel agent with 2 sub-agents
    // Assert: INLINE namespaced merge task exists after JOIN
    // Assert: merge script references parent context and each child's output.context
    // Assert: children's contexts are namespaced under agent names
}
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement — add INLINE namespaced merge task after JOIN**

After the existing `buildParallelAggregateScript` task, add a new INLINE task with explicit `inputParameters` wiring:

```java
// Java: build the INLINE task
Map<String, Object> inputs = new LinkedHashMap<>();
inputs.put("evaluatorType", "graaljs");
inputs.put("parentCtx", "${workflow.variables.context}");
inputs.put("agentNames", agentNamesList);  // e.g., ["web_researcher", "code_analyst"]
for (int i = 0; i < agents.size(); i++) {
    inputs.put("child_" + i, "${" + taskRefs.get(i) + ".output.context}");
}
inputs.put("expression", "(function(){ " +
    "var parent = $.parentCtx || {}; " +
    "var merged = {}; " +
    "for (var k in parent) { if (parent.hasOwnProperty(k)) merged[k] = parent[k]; } " +
    "var agents = $.agentNames; " +
    "for (var i = 0; i < agents.length; i++) { merged[agents[i]] = $['child_' + i] || {}; } " +
    "return merged; })()");
```

Each `$.xxx` in the GraalJS expression maps to an `inputParameters` key. Without this wiring, the script gets `undefined` for everything.

Followed by SET_VARIABLE to persist the merged context.

- [ ] **Step 4: Run tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/MultiAgentCompiler.java server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): parallel strategy namespaced context merge after JOIN"
```

### Task 10: All DO_WHILE strategies — shared context in SET_VARIABLE + test

Covers: **swarm, handoff, manual, router, round_robin, random**

All these strategies use a DO_WHILE loop with SET_VARIABLE. Context handling is identical: initialize context in SET_VARIABLE, pass to sub-workflows, merge output back.

**Files:**
- Modify: `server/.../compiler/MultiAgentCompiler.java`
  - `buildSwarmCaseTasks()` (~line 1255-1300)
  - `compileRotation()` (~line 697-720)
  - `compileHandoff()` (~line 79)
  - `compileManual()` (~line 1091)
  - `compileRouter()` (~line 506-690, SET_VARIABLE init at ~534)
- Modify: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Write compiler tests for each strategy**

```java
@Test void swarm_includesContextInSetVariable() { /* ... */ }
@Test void handoff_includesContextInSetVariable() { /* ... */ }
@Test void manual_includesContextInSetVariable() { /* ... */ }
@Test void router_includesContextInSetVariable() { /* ... */ }
@Test void roundRobin_includesContextInSetVariable() { /* ... */ }
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement for all strategies**

For each DO_WHILE-based strategy:
1. Add `_agent_state` / context to the SET_VARIABLE initialization (alongside `conversation`, `active_agent`)
2. Ensure sub-workflow inputs include `context` (already handled by `compileSubAgent` change in Task 6)
3. After each sub-workflow completes within the loop, merge `output.context` back into shared state

**Router special case:** `compileRouter()` has its own DO_WHILE + SET_VARIABLE (line ~534). Add `_agent_state` to its init vars, matching swarm.

- [ ] **Step 4: Run all context tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 5: Run full server test suite**

Run: `cd server && ./gradlew test`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/MultiAgentCompiler.java server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): all DO_WHILE strategies (swarm/handoff/manual/router/rotation) share context"
```

---

## Chunk 5: Context Size Limits + Security

### Task 11: Server-side context size enforcement

**Files:**
- Modify: `server/.../compiler/AgentCompiler.java` (context injection INLINE task)
- Modify: `server/src/main/resources/application.properties`
- Modify: `server/src/test/.../compiler/ContextPassingTest.java`

- [ ] **Step 1: Add server property**

In `application.properties`:
```properties
agentspan.context.maxSizeBytes=32768
agentspan.context.maxValueSizeBytes=4096
```

- [ ] **Step 2: Add truncation logic to context injection INLINE task**

In the GraalJS script that prepends context to the user message (from Task 7), add:
1. Per-key value truncation: if `JSON.stringify(value).length > maxValueSize`, replace with `value.substring(0, maxValueSize) + "[truncated]"`
2. Total size check: if `JSON.stringify(context).length > maxSize`, drop oldest keys (by insertion order) until under budget
3. Log warning when truncation occurs

- [ ] **Step 3: Write compiler test for truncation**

```java
@Test void contextInjection_truncatesOversizedValues() { /* ... */ }
@Test void contextInjection_dropsOldestKeysWhenOverBudget() { /* ... */ }
```

- [ ] **Step 4: Run tests**

Run: `cd server && ./gradlew test --tests '*ContextPassingTest*'`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java server/src/main/resources/application.properties server/src/test/java/dev/agentspan/runtime/compiler/ContextPassingTest.java
git commit -m "feat(server): context size limits (32KB total, 4KB/key) with truncation"
```

### Task 12: SDK negative / edge-case tests

**Files:**
- Modify: `sdk/python/tests/unit/test_context_passing.py`
- Modify: `sdk/typescript/tests/unit/context-passing.test.ts`

- [ ] **Step 1: Add Python negative tests**

```python
def test_context_key_collision_with_internal_name():
    """Using _state_updates as context_key doesn't corrupt dispatch internals."""
    # Test that the value is stored normally in ToolContext.state

def test_partial_context_preserved_on_tool_failure():
    """If a CLI tool writes to context then fails, earlier writes are preserved."""
    from agentspan.agents.tool import ToolContext
    ctx = ToolContext(execution_id="test", agent_name="test", state={"existing": "value"})
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")
        with pytest.raises(TerminalToolError):
            tool_fn.__wrapped__(command="false", context_key="new_key", context=ctx)
    assert ctx.state == {"existing": "value"}  # existing preserved, new_key not added
```

- [ ] **Step 2: Add TypeScript negative tests**

```typescript
it('preserves existing context state on tool failure', async () => { /* ... */ });
it('handles non-string context_key gracefully', async () => { /* ... */ });
```

- [ ] **Step 3: Run all tests**

Run: `cd sdk/python && uv run pytest tests/unit/test_cli_config.py tests/unit/test_context_passing.py -v`
Run: `cd sdk/typescript && npx vitest run tests/unit/cli-config.test.ts tests/unit/context-passing.test.ts`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add sdk/python/tests/unit/test_context_passing.py sdk/python/tests/unit/test_cli_config.py sdk/typescript/tests/unit/context-passing.test.ts sdk/typescript/tests/unit/cli-config.test.ts
git commit -m "test: negative and edge-case tests for context passing"
```

---

## Chunk 6: E2E Integration Tests

**Prerequisite:** Server must be built and running with all Chunk 3-4 changes.

### Task 13: Python E2E — sequential pipeline context flow

**Files:**
- Create: `sdk/python/tests/e2e/test_context_pipeline.py`

- [ ] **Step 1: Write e2e test — 2-step pipeline with context**

```python
"""E2E test: 2-step pipeline where step_0 writes context, step_1 reads it."""
from agentspan.agents import Agent, AgentRuntime, tool, ToolContext

@tool
def save_value(value: str, context: ToolContext) -> dict:
    """Save a value to context."""
    context.state["saved_value"] = value
    return {"saved": value}

step_0 = Agent(
    name="writer",
    model="openai/gpt-4o-mini",
    instructions="Call save_value with value='hello_from_step_0'. Then say 'done'.",
    tools=[save_value],
)

step_1 = Agent(
    name="reader",
    model="openai/gpt-4o-mini",
    instructions="Read the 'saved_value' from the Context block and repeat it exactly in your response.",
)

pipeline = step_0 >> step_1

def test_context_flows_through_pipeline():
    with AgentRuntime() as rt:
        result = rt.run(pipeline, "Go")
        assert result.is_success
        assert "hello_from_step_0" in str(result.output).lower()
```

- [ ] **Step 2: Rebuild and restart server**

Run: `cd server && ./gradlew bootJar && java -jar build/libs/server*.jar &`

- [ ] **Step 3: Run the test**

Run: `cd sdk/python && uv run pytest tests/e2e/test_context_pipeline.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add sdk/python/tests/e2e/test_context_pipeline.py
git commit -m "test(python): e2e test for sequential pipeline context flow"
```

### Task 14: TypeScript E2E — sequential pipeline context flow

**Files:**
- Create: `sdk/typescript/tests/e2e/context-pipeline.test.ts`

- [ ] **Step 1: Write equivalent e2e test**

Same pattern: 2-step pipeline, step_0 tool writes `saved_value` to context, step_1 reads from injected context JSON.

- [ ] **Step 2: Run the test**

Run: `cd sdk/typescript && npx vitest run tests/e2e/context-pipeline.test.ts`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add sdk/typescript/tests/e2e/context-pipeline.test.ts
git commit -m "test(typescript): e2e test for sequential pipeline context flow"
```

### Task 15: Run full regression

- [ ] **Step 1: Python quickstart harness**

Run: `cd sdk/python && uv run python examples/quickstart/run_all.py`
Expected: 4 passed, 0 failed

- [ ] **Step 2: TypeScript quickstart harness**

Run: `cd sdk/typescript && npx tsx examples/quickstart/run-all.ts`
Expected: 4 passed, 0 failed

- [ ] **Step 3: Server test suite**

Run: `cd server && ./gradlew test`
Expected: All pass

---

## Chunk 7: Update Examples

### Task 16: Update `61-github-coding-agent-chained` for both SDKs

**Files:**
- Modify: `sdk/typescript/examples/61-github-coding-agent-chained.ts`
- Modify: `sdk/python/examples/61_github_coding_agent_chained.py`

- [ ] **Step 1: Update `git_fetch_issues` instructions to use `context_key`**

Add instructions telling the LLM to save values with `context_key`:
```
"   - When running mktemp, set context_key='working_dir'\n"
"   - When cloning, set context_key='repo' to confirm the repo name\n"
"   - When creating branch, set context_key='branch' to confirm the branch name\n"
```

- [ ] **Step 2: Update `git_push_pr` allowed commands**

Fix the bug found in the execution analysis — add `'git'` to allowed commands:
```typescript
cliConfig: { enabled: true, allowedCommands: ['gh', 'git'] },
```

- [ ] **Step 3: Update BOTH Python and TypeScript examples identically**

- [ ] **Step 4: Commit**

```bash
git add sdk/typescript/examples/61-github-coding-agent-chained.ts sdk/python/examples/61_github_coding_agent_chained.py
git commit -m "fix: update chained agent for context_key, add git to push agent allowed commands"
```
