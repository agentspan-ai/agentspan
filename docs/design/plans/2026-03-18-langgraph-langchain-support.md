# LangGraph & LangChain Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add support for running LangGraph `CompiledStateGraph` and LangChain `AgentExecutor` objects on Agentspan as black-box passthrough workers with SSE streaming.

**Architecture:** LangGraph/LangChain manage their own LLM calls internally, so they cannot use the existing OpenAI/ADK path that extracts tools and uses `LLM_CHAT_COMPLETE` tasks. Instead, each graph/executor becomes a single Conductor SIMPLE task (a "passthrough execution"). Intermediate node events are pushed non-blocking via HTTP POST to `POST /api/agent/events/{executionId}`, which fans them out to SSE clients.

**Tech Stack:** Python (langgraph, langchain), Java 17 / Spring Boot, Netflix Conductor, SSE (SseEmitter), pytest, JUnit 5 + AssertJ.

**Spec:** `docs/superpowers/specs/2026-03-18-langgraph-langchain-support-design.md`

---

## Chunk 1: Server Infrastructure

### Task 1: `LangGraphNormalizer.java`

**Files:**
- Create: `server/src/main/java/dev/agentspan/runtime/normalizer/LangGraphNormalizer.java`
- Create: `server/src/test/java/dev/agentspan/runtime/normalizer/LangGraphNormalizerTest.java`

- [ ] **Step 1: Write the failing test**

```java
// server/src/test/java/dev/agentspan/runtime/normalizer/LangGraphNormalizerTest.java
package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;

class LangGraphNormalizerTest {

    private final LangGraphNormalizer normalizer = new LangGraphNormalizer();

    @Test
    void frameworkIdIsLanggraph() {
        assertThat(normalizer.frameworkId()).isEqualTo("langgraph");
    }

    @Test
    void normalizeProducesPassthroughConfig() {
        Map<String, Object> raw = Map.of(
            "name", "my_graph",
            "_worker_name", "my_graph"
        );

        AgentConfig config = normalizer.normalize(raw);

        assertThat(config.getName()).isEqualTo("my_graph");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_graph");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void normalizeUsesDefaultNameWhenMissing() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("langgraph_agent");
        assertThat(config.getTools().get(0).getName()).isEqualTo("langgraph_agent");
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd server && ./gradlew test --tests LangGraphNormalizerTest -q 2>&1 | tail -20
```

Expected: FAIL — `LangGraphNormalizer` does not exist.

- [ ] **Step 3: Implement `LangGraphNormalizer.java`**

```java
// server/src/main/java/dev/agentspan/runtime/normalizer/LangGraphNormalizer.java
package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Normalizes LangGraph rawConfig into a passthrough AgentConfig.
 * The passthrough workflow has one SIMPLE task wrapping the entire graph.
 */
@Component
public class LangGraphNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(LangGraphNormalizer.class);
    private static final String DEFAULT_NAME = "langgraph_agent";

    @Override
    public String frameworkId() {
        return "langgraph";
    }

    @Override
    public AgentConfig normalize(Map<String, Object> raw) {
        String name = getString(raw, "name", DEFAULT_NAME);
        String workerName = getString(raw, "_worker_name", name);
        log.info("Normalizing LangGraph agent: {}", name);

        AgentConfig config = new AgentConfig();
        config.setName(name);
        // model is intentionally null — passthrough path does not call LLM_CHAT_COMPLETE

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("_framework_passthrough", true);
        config.setMetadata(metadata);

        ToolConfig worker = ToolConfig.builder()
            .name(workerName)
            .description("LangGraph passthrough worker")
            .toolType("worker")
            .build();
        config.setTools(List.of(worker));

        return config;
    }

    private String getString(Map<String, Object> map, String key, String defaultValue) {
        Object v = map.get(key);
        return v instanceof String ? (String) v : defaultValue;
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd server && ./gradlew test --tests LangGraphNormalizerTest -q 2>&1 | tail -10
```

Expected: BUILD SUCCESS, all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/normalizer/LangGraphNormalizer.java \
        server/src/test/java/dev/agentspan/runtime/normalizer/LangGraphNormalizerTest.java
git commit -m "feat(server): add LangGraphNormalizer for passthrough workflow"
```

---

### Task 2: `LangChainNormalizer.java`

**Files:**
- Create: `server/src/main/java/dev/agentspan/runtime/normalizer/LangChainNormalizer.java`
- Create: `server/src/test/java/dev/agentspan/runtime/normalizer/LangChainNormalizerTest.java`

- [ ] **Step 1: Write the failing test**

```java
// server/src/test/java/dev/agentspan/runtime/normalizer/LangChainNormalizerTest.java
package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;

class LangChainNormalizerTest {

    private final LangChainNormalizer normalizer = new LangChainNormalizer();

    @Test
    void frameworkIdIsLangchain() {
        assertThat(normalizer.frameworkId()).isEqualTo("langchain");
    }

    @Test
    void normalizeProducesPassthroughConfig() {
        Map<String, Object> raw = Map.of(
            "name", "my_executor",
            "_worker_name", "my_executor"
        );

        AgentConfig config = normalizer.normalize(raw);

        assertThat(config.getName()).isEqualTo("my_executor");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_executor");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void normalizeUsesDefaultNameWhenMissing() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("langchain_agent");
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd server && ./gradlew test --tests LangChainNormalizerTest -q 2>&1 | tail -10
```

Expected: FAIL — class does not exist.

- [ ] **Step 3: Implement `LangChainNormalizer.java`**

```java
// server/src/main/java/dev/agentspan/runtime/normalizer/LangChainNormalizer.java
package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Normalizes LangChain AgentExecutor rawConfig into a passthrough AgentConfig.
 */
@Component
public class LangChainNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(LangChainNormalizer.class);
    private static final String DEFAULT_NAME = "langchain_agent";

    @Override
    public String frameworkId() {
        return "langchain";
    }

    @Override
    public AgentConfig normalize(Map<String, Object> raw) {
        String name = getString(raw, "name", DEFAULT_NAME);
        String workerName = getString(raw, "_worker_name", name);
        log.info("Normalizing LangChain agent: {}", name);

        AgentConfig config = new AgentConfig();
        config.setName(name);

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("_framework_passthrough", true);
        config.setMetadata(metadata);

        ToolConfig worker = ToolConfig.builder()
            .name(workerName)
            .description("LangChain passthrough worker")
            .toolType("worker")
            .build();
        config.setTools(List.of(worker));

        return config;
    }

    private String getString(Map<String, Object> map, String key, String defaultValue) {
        Object v = map.get(key);
        return v instanceof String ? (String) v : defaultValue;
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd server && ./gradlew test --tests LangChainNormalizerTest -q 2>&1 | tail -10
```

Expected: BUILD SUCCESS.

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/normalizer/LangChainNormalizer.java \
        server/src/test/java/dev/agentspan/runtime/normalizer/LangChainNormalizerTest.java
git commit -m "feat(server): add LangChainNormalizer for passthrough workflow"
```

---

### Task 3: `AgentCompiler` passthrough path

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java`
- Modify: `server/src/test/java/dev/agentspan/runtime/compiler/AgentCompilerTest.java`

- [ ] **Step 1: Write the failing test**

Add to the bottom of `AgentCompilerTest.java` (before the closing `}`):

```java
@Test
void testCompileFrameworkPassthrough() {
    // Build a passthrough AgentConfig as produced by LangGraphNormalizer
    dev.agentspan.runtime.model.ToolConfig worker = dev.agentspan.runtime.model.ToolConfig.builder()
        .name("my_graph")
        .toolType("worker")
        .build();

    AgentConfig config = AgentConfig.builder()
        .name("my_graph")
        .metadata(Map.of("_framework_passthrough", true))
        .tools(List.of(worker))
        .build();

    WorkflowDef wf = compiler.compile(config);

    assertThat(wf.getName()).isEqualTo("my_graph");
    assertThat(wf.getTasks()).hasSize(1);
    WorkflowTask task = wf.getTasks().get(0);
    assertThat(task.getType()).isEqualTo("SIMPLE");
    assertThat(task.getName()).isEqualTo("my_graph");
    assertThat(task.getTaskReferenceName()).isEqualTo("_fw_task");
    // prompt/session_id/media must be wired from workflow input
    assertThat(task.getInputParameters().get("prompt")).isEqualTo("${workflow.input.prompt}");
    assertThat(task.getInputParameters().get("session_id")).isEqualTo("${workflow.input.session_id}");
    // Output must reference the _fw_task
    assertThat(wf.getOutputParameters().get("result")).isEqualTo("${_fw_task.output.result}");
}

@Test
void testPassthroughGuardPreventsCrashOnNullModel() {
    // Passthrough configs have no model — this must NOT throw
    AgentConfig config = AgentConfig.builder()
        .name("my_graph")
        .metadata(Map.of("_framework_passthrough", true))
        .tools(List.of(dev.agentspan.runtime.model.ToolConfig.builder()
            .name("my_graph").toolType("worker").build()))
        .build();

    assertThatNoException().isThrownBy(() -> compiler.compile(config));
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && ./gradlew test --tests "AgentCompilerTest.testCompileFrameworkPassthrough" --tests "AgentCompilerTest.testPassthroughGuardPreventsCrashOnNullModel" -q 2>&1 | tail -20
```

Expected: `testCompileFrameworkPassthrough` fails because `compileFrameworkPassthrough()` doesn't exist. `testPassthroughGuardPreventsCrashOnNullModel` fails with `NullPointerException` from `ModelParser.parse(null)` inside `compileSimple()` — this is the correct TDD signal that the passthrough guard is missing.

- [ ] **Step 3: Implement `compileFrameworkPassthrough()` in `AgentCompiler.java`**

In `compile()` at line 42, add the passthrough guard as the **very first check** (before `config.isExternal()`):

```java
public WorkflowDef compile(AgentConfig config) {
    // Passthrough check MUST be first — passthrough configs have null model.
    // Any other branch (isExternal, hasTools) would crash on null model.
    if (isFrameworkPassthrough(config)) {
        return compileFrameworkPassthrough(config);
    }

    if (config.isExternal()) {
        // ... existing code unchanged
```

Add these two private methods anywhere in the class (after the existing private methods):

```java
private boolean isFrameworkPassthrough(AgentConfig config) {
    return config.getMetadata() != null
        && Boolean.TRUE.equals(config.getMetadata().get("_framework_passthrough"));
}

private WorkflowDef compileFrameworkPassthrough(AgentConfig config) {
    log.debug("Compiling framework passthrough workflow: {}", config.getName());

    String workerName = config.getTools().get(0).getName();

    WorkflowTask fwTask = new WorkflowTask();
    fwTask.setType("SIMPLE");
    fwTask.setName(workerName);
    fwTask.setTaskReferenceName("_fw_task");
    fwTask.setInputParameters(new LinkedHashMap<>(Map.of(
        "prompt",     "${workflow.input.prompt}",
        "session_id", "${workflow.input.session_id}",
        "media",      "${workflow.input.media}"
    )));

    WorkflowDef wf = new WorkflowDef();
    wf.setName(config.getName());
    wf.setVersion(1);
    wf.setInputParameters(new ArrayList<>(WORKFLOW_INPUTS));
    wf.setTasks(List.of(fwTask));
    wf.setOutputParameters(Map.of("result", "${_fw_task.output.result}"));

    Map<String, Object> metadata = config.getMetadata() != null
        ? new LinkedHashMap<>(config.getMetadata()) : new LinkedHashMap<>();
    wf.setMetadata(metadata);

    return wf;
}
```

- [ ] **Step 4: Run all compiler tests**

```bash
cd server && ./gradlew test --tests AgentCompilerTest -q 2>&1 | tail -10
```

Expected: BUILD SUCCESS, all tests pass (including existing tests — the guard is first so nothing regresses).

- [ ] **Step 5: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java \
        server/src/test/java/dev/agentspan/runtime/compiler/AgentCompilerTest.java
git commit -m "feat(server): add passthrough compilation path for LangGraph/LangChain"
```

---

### Task 4: `AgentEventListener` `_fw_` prefix guard

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/service/AgentEventListener.java`
- Modify: `server/src/test/java/dev/agentspan/runtime/service/AgentEventListenerTest.java`

- [ ] **Step 1: Write the failing test**

`AgentEventListener` has one constructor: `AgentEventListener(AgentStreamRegistry streamRegistry)`. The existing `AgentEventListenerTest.java` (see `server/src/test/java/dev/agentspan/runtime/service/AgentEventListenerTest.java`) already follows the correct pattern. Follow it exactly.

We test the observable behavior: `onTaskCompleted` should NOT call `streamRegistry.send()` with a `tool_call` event for a `_fw_task`. Add to the existing `AgentEventListenerTest.java` file (do NOT create a new file):

```java
// Add to AgentEventListenerTest.java (below existing tests)

@Test
void onTaskCompleted_fwPrefixedTaskDoesNotEmitToolEvent() {
    TaskModel task = makeTask("wf-fw", "SIMPLE", "_fw_task");

    listener.onTaskCompleted(task);

    // No tool_call or tool_result events should be sent for _fw_ tasks
    verify(streamRegistry, never()).send(any(), any());
}

@Test
void onTaskCompleted_regularSimpleTaskEmitsToolResult() {
    TaskModel task = makeTask("wf-tool", "SIMPLE", "search_tool");
    // Simulate task output that triggers tool_result
    task.setOutputData(Map.of("result", "found it"));

    listener.onTaskCompleted(task);

    ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
    verify(streamRegistry).send(eq("wf-tool"), captor.capture());
    assertThat(captor.getValue().getType()).isEqualTo("tool_result");
}
```

> Note: Read the existing `onTaskCompleted` implementation first to confirm what events it sends for a completed SIMPLE task. The exact assertion for `regularSimpleTaskEmitsToolResult` depends on the current code behavior — adjust if needed.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd server && ./gradlew test --tests "AgentEventListenerTest.onTaskCompleted_fwPrefixedTaskDoesNotEmitToolEvent" -q 2>&1 | tail -20
```

Expected: FAIL — the test asserts `never()` but the listener currently emits events for all SIMPLE tasks.

- [ ] **Step 3: Add `_fw_` guard to `AgentEventListener.isToolTask()` (line 217)**

Current `isToolTask()` is at line 217. Add the `_fw_` guard immediately after the null check on `taskType`:

```java
private boolean isToolTask(TaskModel task) {
    String taskType = task.getTaskType();
    if (taskType == null) return false;
    // Skip framework passthrough wrapper tasks — they emit their own fine-grained events
    if (task.getReferenceTaskName() != null && task.getReferenceTaskName().startsWith("_fw_")) {
        return false;
    }
    switch (taskType) {
        // ... existing cases unchanged (LLM_CHAT_COMPLETE, SWITCH, etc.) ...
    }
}
```

Keep `isToolTask` as `private` — it is tested indirectly via `onTaskCompleted`.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd server && ./gradlew test --tests AgentEventListenerTest -q 2>&1 | tail -10
```

Expected: BUILD SUCCESS, all listener tests pass.

- [ ] **Step 5: Run full server test suite**

```bash
cd server && ./gradlew test -q 2>&1 | tail -20
```

Expected: BUILD SUCCESS.

- [ ] **Step 6: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/service/AgentEventListener.java \
        server/src/test/java/dev/agentspan/runtime/service/AgentEventListenerTest.java
git commit -m "feat(server): suppress spurious tool events for _fw_ passthrough tasks"
```

---

### Task 5: Event push endpoint and `pushFrameworkEvent()`

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/controller/AgentController.java`
- Modify: `server/src/main/java/dev/agentspan/runtime/service/AgentService.java`
- Create: `server/src/test/java/dev/agentspan/runtime/controller/EventPushEndpointTest.java`

There are two tests to write:

**Part A**: Unit test for `AgentService.pushFrameworkEvent()` (no Spring context needed — same pattern as `AgentEventListenerTest`):

```java
// server/src/test/java/dev/agentspan/runtime/service/AgentServicePushEventTest.java
package dev.agentspan.runtime.service;

import dev.agentspan.runtime.model.AgentSSEEvent;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Map;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class AgentServicePushEventTest {

    // Test AgentService.pushFrameworkEvent() in isolation.
    // We call the method directly and verify streamRegistry.send() is called correctly.
    // AgentService requires many Spring dependencies — test only the push method
    // by extracting the logic into a static helper or testing via a thin wrapper.
    // SIMPLEST: extract pushFrameworkEvent logic into a package-private static
    // method for testing, or test via a direct instantiation if possible.
    //
    // Because AgentService uses @RequiredArgsConstructor and has many deps,
    // the easiest approach is to test the event translation logic directly.
    // Read AgentService.java to see if pushFrameworkEvent can be extracted.
    // If it cannot, test it via the E2E approach below.
}
```

> **Decision**: After reading `AgentService.java`, if `pushFrameworkEvent` can't be tested in isolation cleanly, skip the unit test and cover it in the E2E test below. Do NOT write a brittle partial-mock test.

**Part B**: E2E test for the endpoint — follow the exact pattern of `AgentCompileE2ETest.java` (uses `@SpringBootTest` with full context):

```java
// server/src/test/java/dev/agentspan/runtime/controller/EventPushEndpointTest.java
package dev.agentspan.runtime.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.conductoross.conductor.AgentRuntime;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest(
        classes = AgentRuntime.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("test")
class EventPushEndpointTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    private int postEvent(String executionId, Map<String, Object> body) throws Exception {
        URI uri = URI.create("http://localhost:" + port + "/api/agent/events/" + executionId);
        HttpURLConnection conn = (HttpURLConnection) uri.toURL().openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(MAPPER.writeValueAsBytes(body));
        }
        return conn.getResponseCode();
    }

    @Test
    void pushThinkingEventReturns200() throws Exception {
        int status = postEvent("wf-test-123", Map.of(
            "type", "thinking",
            "content", "Processing node agent"
        ));
        assertThat(status).isEqualTo(200);
    }

    @Test
    void pushToolCallEventReturns200() throws Exception {
        int status = postEvent("wf-test-456", Map.of(
            "type", "tool_call",
            "toolName", "search",
            "args", Map.of("query", "test")
        ));
        assertThat(status).isEqualTo(200);
    }

    @Test
    void pushEventForUnknownWorkflowStillReturns200() throws Exception {
        // Events for workflows with no SSE listeners are silently dropped
        int status = postEvent("nonexistent-wf", Map.of("type", "thinking", "content", "x"));
        assertThat(status).isEqualTo(200);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd server && ./gradlew test --tests EventPushEndpointTest -q 2>&1 | tail -20
```

Expected: FAIL — 404 (endpoint does not exist yet).

- [ ] **Step 3: Add endpoint to `AgentController.java`**

Add after the existing endpoints (e.g., after the `/{executionId}/respond` endpoint):

```java
/**
 * Receive an SSE event pushed by a framework worker (LangGraph/LangChain).
 * Always returns 200 — unknown executionIds are silently dropped.
 *
 * <p>Body: {@code {"type": "thinking|tool_call|tool_result", "content": "...",
 * "toolName": "...", "args": {...}, "result": "..."}}</p>
 */
@PostMapping("/events/{executionId}")
public void pushFrameworkEvent(
        @PathVariable String executionId,
        @RequestBody Map<String, Object> event) {
    agentService.pushFrameworkEvent(executionId, event);
}
```

- [ ] **Step 4: Add `pushFrameworkEvent()` to `AgentService.java`**

Read `AgentSSEEvent.java` to see which factory methods exist before implementing:
```bash
find server/src/main -name "AgentSSEEvent.java"
cat server/src/main/java/dev/agentspan/runtime/model/AgentSSEEvent.java
```

Then add to `AgentService.java`:

```java
/**
 * Translate a framework event map (from Python worker HTTP push) to an
 * AgentSSEEvent and fan it out to all registered SSE emitters.
 *
 * <p>Silently ignored if no clients are connected (streamRegistry drops it).</p>
 */
public void pushFrameworkEvent(String executionId, Map<String, Object> event) {
    String type = event.getOrDefault("type", "").toString();
    AgentSSEEvent sseEvent = switch (type) {
        case "thinking" -> AgentSSEEvent.thinking(executionId,
            event.getOrDefault("content", "").toString());
        case "tool_call" -> AgentSSEEvent.toolCall(executionId,
            event.getOrDefault("toolName", "").toString(),
            event.get("args"));
        case "tool_result" -> AgentSSEEvent.toolResult(executionId,
            event.getOrDefault("toolName", "").toString(),
            event.getOrDefault("result", "").toString());
        default -> {
            log.debug("Unknown framework event type '{}' for execution {}", type, executionId);
            yield null;
        }
    };
    if (sseEvent != null) {
        streamRegistry.send(executionId, sseEvent);
    }
}
```

> Note: After reading `AgentSSEEvent.java`, adjust the factory method calls to match the actual method signatures. The spec says `thinking(executionId, content)`, `toolCall(executionId, toolName, args)`, `toolResult(executionId, toolName, content)`.

- [ ] **Step 5: Run endpoint test**

```bash
cd server && ./gradlew test --tests EventPushEndpointTest -q 2>&1 | tail -10
```

Expected: BUILD SUCCESS, 3 tests pass.

- [ ] **Step 6: Run full server test suite**

```bash
cd server && ./gradlew test -q 2>&1 | tail -20
```

Expected: BUILD SUCCESS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/controller/AgentController.java \
        server/src/main/java/dev/agentspan/runtime/service/AgentService.java \
        server/src/test/java/dev/agentspan/runtime/controller/EventPushEndpointTest.java \
        server/src/test/java/dev/agentspan/runtime/service/AgentServicePushEventTest.java
git commit -m "feat(server): add POST /api/agent/events/{executionId} for framework event push"
```

---

## Chunk 2: Python SDK Infrastructure

> **Prerequisite for all Tasks in this Chunk:** Install langgraph and langchain-core as dev dependencies before writing any tests. Tasks 7 and 8 import from these packages in their test files.

```bash
cd sdk/python && uv add --dev langgraph langchain-core langchain langchain-openai
```

### Task 6: Framework detection in `serializer.py`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/serializer.py`
- Create: `sdk/python/tests/unit/test_framework_detection.py`

- [ ] **Step 1: Write the failing tests**

```python
# sdk/python/tests/unit/test_framework_detection.py
"""Tests for LangGraph/LangChain framework auto-detection in serializer.py."""
import pytest
from unittest.mock import MagicMock


def _make_obj_with_class_name(class_name: str):
    """Create a mock object whose type(obj).__name__ is class_name."""
    obj = MagicMock()
    type(obj).__name__ = class_name
    return obj


def test_detect_compiled_state_graph():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("CompiledStateGraph")
    assert detect_framework(obj) == "langgraph"


def test_detect_pregel():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("Pregel")
    assert detect_framework(obj) == "langgraph"


def test_detect_agent_executor():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("AgentExecutor")
    assert detect_framework(obj) == "langchain"


def test_openai_agent_still_detected():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = MagicMock()
    type(obj).__name__ = "Agent"
    type(obj).__module__ = "agents.core"
    assert detect_framework(obj) == "openai"


def test_native_agent_returns_none():
    from agentspan.agents.frameworks.serializer import detect_framework
    from agentspan.agents.agent import Agent
    # MagicMock(spec=Agent) does NOT pass isinstance(obj, Agent).
    # Patch isinstance to return True, or subclass Agent minimally.
    # Simplest: patch detect_framework's isinstance call using monkeypatch.
    # We test the module-prefix fallback returning None for unknown modules instead.
    obj = MagicMock()
    type(obj).__name__ = "Agent"
    type(obj).__module__ = "agentspan.agents.agent"
    # This will hit the module-prefix lookup and return None (no prefix match)
    result = detect_framework(obj)
    assert result is None


def test_unknown_object_returns_none():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("SomeRandomClass")
    type(obj).__module__ = "some.unknown.module"
    assert detect_framework(obj) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk/python && uv run pytest tests/unit/test_framework_detection.py -v 2>&1 | tail -20
```

Expected: FAIL — `detect_framework` returns `None` for LangGraph/LangChain objects.

- [ ] **Step 3: Update `detect_framework()` in `serializer.py`**

Replace the current `detect_framework()` function (lines 33-48) with:

```python
def detect_framework(agent_obj: Any) -> Optional[str]:
    """Detect the agent framework from the object's type name and module.

    Returns the framework identifier (e.g. ``"openai"``, ``"google_adk"``,
    ``"langgraph"``, ``"langchain"``) or ``None`` for native Conductor Agents.
    """
    # Native Agent — no normalization needed
    from agentspan.agents.agent import Agent
    if isinstance(agent_obj, Agent):
        return None

    # Precise type-name check for LangGraph (avoid fragile module prefix matching
    # since langgraph uses internal Pregel/CompiledStateGraph class names)
    type_name = type(agent_obj).__name__
    if type_name in ("CompiledStateGraph", "Pregel", "CompiledGraph"):
        return "langgraph"

    # LangChain AgentExecutor
    if type_name == "AgentExecutor":
        return "langchain"

    # Existing module-prefix fallback for openai and google_adk
    module = type(agent_obj).__module__ or ""
    for prefix, framework_id in _FRAMEWORK_DETECTION.items():
        if module == prefix or module.startswith(prefix + "."):
            return framework_id
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sdk/python && uv run pytest tests/unit/test_framework_detection.py -v 2>&1 | tail -20
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full unit test suite to check for regressions**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/serializer.py \
        sdk/python/tests/unit/test_framework_detection.py
git commit -m "feat(python): detect LangGraph/LangChain by type name in serializer"
```

---

### Task 7: `frameworks/langgraph.py`

**Files:**
- Create: `sdk/python/src/agentspan/agents/frameworks/langgraph.py`
- Create: `sdk/python/tests/unit/test_langgraph_worker.py`

**Context:** The worker calls `graph.stream(input, config, stream_mode=["updates","values"])`. Each chunk is a tuple `(stream_mode, chunk_data)`. For `"updates"` chunks, push SSE events non-blocking. For `"values"` chunks, keep the last one as the final state. Input is auto-detected via `graph.get_input_jsonschema()`.

- [ ] **Step 1: Write failing unit tests**

```python
# sdk/python/tests/unit/test_langgraph_worker.py
"""Unit tests for the LangGraph passthrough worker."""
import pytest
from unittest.mock import MagicMock, patch, call


def _make_fake_graph(stream_chunks=None, input_schema=None):
    """Create a mock CompiledStateGraph."""
    graph = MagicMock()
    type(graph).__name__ = "CompiledStateGraph"
    graph.name = "test_graph"

    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "messages": {"type": "array"}
            }
        }
    graph.get_input_jsonschema.return_value = input_schema

    if stream_chunks is None:
        # Default: one updates chunk (node result), one values chunk (final state)
        stream_chunks = [
            ("updates", {"agent": {"messages": []}}),
            ("values", {"messages": [
                {"type": "ai", "content": "Hello!", "tool_calls": []}
            ]}),
        ]
    graph.stream.return_value = iter(stream_chunks)
    return graph


def _make_task(prompt="Hello", session_id="", execution_id="wf-123"):
    from conductor.client.http.models.task import Task
    task = MagicMock(spec=Task)
    task.input_data = {"prompt": prompt, "session_id": session_id}
    task.workflow_instance_id = execution_id
    return task


class TestSerializeLanggraph:
    def test_returns_single_worker_info(self):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        graph = _make_fake_graph()

        raw_config, workers = serialize_langgraph(graph)

        assert len(workers) == 1
        assert workers[0].name == "test_graph"

    def test_raw_config_has_name_and_worker_name(self):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        graph = _make_fake_graph()

        raw_config, _ = serialize_langgraph(graph)

        assert raw_config["name"] == "test_graph"
        assert raw_config["_worker_name"] == "test_graph"

    def test_graph_with_no_name_uses_default(self):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        graph = _make_fake_graph()
        graph.name = None  # graph has no .name attribute

        raw_config, workers = serialize_langgraph(graph)

        assert raw_config["name"] == "langgraph_agent"


class TestMakeLanggraphWorker:
    def test_worker_extracts_output_from_messages_state(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        # Graph with messages-based state — last AIMessage content is the output
        chunks = [
            ("updates", {"agent": {"messages": []}}),
            ("values", {"messages": [
                {"type": "human", "content": "Hello"},
                {"type": "ai", "content": "World!", "tool_calls": []},
            ]}),
        ]
        graph = _make_fake_graph(stream_chunks=chunks)
        task = _make_task(prompt="Hello")

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "World!"

    def test_worker_uses_session_id_as_thread_id(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph = _make_fake_graph()
        task = _make_task(session_id="sess-42")

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:6767", "key", "secret"
            )
            worker_fn(task)

        # graph.stream must have been called with configurable.thread_id = "sess-42"
        call_kwargs = graph.stream.call_args
        config_arg = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("config")
        assert config_arg["configurable"]["thread_id"] == "sess-42"

    def test_worker_returns_failed_on_exception(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph = _make_fake_graph()
        graph.stream.side_effect = RuntimeError("checkpointer not set")
        task = _make_task()

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "checkpointer not set" in result.reason_for_incompletion

    def test_worker_pushes_thinking_event_for_node_update(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        chunks = [
            ("updates", {"agent": {"messages": []}}),
            ("values", {"messages": [
                {"type": "ai", "content": "Done", "tool_calls": []}
            ]}),
        ]
        graph = _make_fake_graph(stream_chunks=chunks)
        task = _make_task()

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking") as mock_push:
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:6767", "key", "secret"
            )
            worker_fn(task)

        # Should have pushed at least one thinking event for the "agent" node
        push_calls = mock_push.call_args_list
        event_types = [c[0][1]["type"] for c in push_calls]
        assert "thinking" in event_types

    def test_worker_detects_messages_input_format(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker
        from langchain_core.messages import HumanMessage  # local import: langchain_core installed as dev dep

        graph = _make_fake_graph(input_schema={
            "type": "object",
            "properties": {"messages": {"type": "array"}},
            "required": ["messages"]
        })
        task = _make_task(prompt="test input")

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:6767", "key", "secret"
            )
            worker_fn(task)

        # graph.stream must have been called with {"messages": [HumanMessage(...)]}
        input_arg = graph.stream.call_args[0][0]
        assert "messages" in input_arg
        assert isinstance(input_arg["messages"][0], HumanMessage)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk/python && uv run pytest tests/unit/test_langgraph_worker.py -v 2>&1 | tail -30
```

Expected: FAIL — module `agentspan.agents.frameworks.langgraph` does not exist.

- [ ] **Step 3: Implement `frameworks/langgraph.py`**

```python
# sdk/python/src/agentspan/agents/frameworks/langgraph.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangGraph passthrough worker support.

Provides:
- serialize_langgraph(graph) -> (raw_config, [WorkerInfo])
- make_langgraph_worker(graph, name, server_url, auth_key, auth_secret) -> tool_worker
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.langgraph")

# Shared thread pool for non-blocking event push (process lifetime)
_EVENT_PUSH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph-event-push")

_DEFAULT_NAME = "langgraph_agent"


def serialize_langgraph(graph: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a CompiledStateGraph into (raw_config, [WorkerInfo]).

    The WorkerInfo contains a pre-wrapped tool_worker — it does NOT go through
    make_tool_worker to avoid double-wrapping.
    """
    name = getattr(graph, "name", None) or _DEFAULT_NAME
    raw_config = {"name": name, "_worker_name": name}

    # server_url/auth will be injected at registration time via closure
    # For serialization we only need the name
    worker = WorkerInfo(
        name=name,
        description=f"LangGraph passthrough worker for {name}",
        input_schema={"type": "object", "properties": {
            "prompt": {"type": "string"},
            "session_id": {"type": "string"},
        }},
        func=None,  # placeholder — replaced at registration time
    )
    return raw_config, [worker]


def make_langgraph_worker(
    graph: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Any:
    """Build a pre-wrapped tool_worker(task) -> TaskResult for a LangGraph graph.

    The returned function has the correct signature for @worker_task registration
    and does NOT go through make_tool_worker.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def tool_worker(task: Task) -> TaskResult:
        execution_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        session_id = (task.input_data.get("session_id") or "").strip()

        try:
            graph_input = _build_input(graph, prompt)
            config = {}
            if session_id:
                config = {"configurable": {"thread_id": session_id}}

            final_state = None
            for mode, chunk in graph.stream(graph_input, config, stream_mode=["updates", "values"]):
                if mode == "updates":
                    _process_updates_chunk(chunk, execution_id, server_url, auth_key, auth_secret)
                elif mode == "values":
                    final_state = chunk

            output = _extract_output(final_state)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"result": output},
            )

        except Exception as exc:
            logger.error("LangGraph worker error (execution_id=%s): %s", execution_id, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )

    return tool_worker


def _build_input(graph: Any, prompt: str) -> Dict[str, Any]:
    """Auto-detect input format from graph's JSON schema."""
    try:
        schema = graph.get_input_jsonschema()
        props = schema.get("properties", {})
        if "messages" in props:
            from langchain_core.messages import HumanMessage
            return {"messages": [HumanMessage(content=prompt)]}
        # Find first required string property
        required = schema.get("required", list(props.keys()))
        for key in required:
            prop = props.get(key, {})
            if prop.get("type") == "string":
                return {key: prompt}
    except Exception:
        pass
    return {"prompt": prompt}


def _process_updates_chunk(
    chunk: Dict[str, Any],
    execution_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Map a LangGraph 'updates' chunk to Agentspan SSE events and push non-blocking."""
    for node_name, state_updates in chunk.items():
        # Always emit a thinking event for each node execution
        _push_event_nonblocking(
            execution_id,
            {"type": "thinking", "content": node_name},
            server_url, auth_key, auth_secret,
        )

        # Check for tool calls and tool results in messages
        messages = state_updates.get("messages", []) if isinstance(state_updates, dict) else []
        for msg in (messages if isinstance(messages, list) else []):
            _emit_message_events(msg, execution_id, server_url, auth_key, auth_secret)


def _emit_message_events(
    msg: Any,
    execution_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Emit tool_call / tool_result events from a LangChain message object or dict."""
    # Handle both dict-style (from stream) and object-style messages
    msg_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
    if msg_type == "tool":
        # ToolMessage = tool result
        name = getattr(msg, "name", None) or (msg.get("name", "") if isinstance(msg, dict) else "")
        content = getattr(msg, "content", "") or (msg.get("content", "") if isinstance(msg, dict) else "")
        _push_event_nonblocking(
            execution_id,
            {"type": "tool_result", "toolName": name, "result": str(content)},
            server_url, auth_key, auth_secret,
        )
    elif msg_type == "ai":
        # AIMessage — check for tool calls
        tool_calls = getattr(msg, "tool_calls", None) or (
            msg.get("tool_calls", []) if isinstance(msg, dict) else []
        )
        for tc in (tool_calls or []):
            tc_name = getattr(tc, "name", None) or (tc.get("name", "") if isinstance(tc, dict) else "")
            tc_args = getattr(tc, "args", {}) or (tc.get("args", {}) if isinstance(tc, dict) else {})
            _push_event_nonblocking(
                execution_id,
                {"type": "tool_call", "toolName": tc_name, "args": tc_args},
                server_url, auth_key, auth_secret,
            )


def _extract_output(final_state: Optional[Dict[str, Any]]) -> str:
    """Extract the agent's final text output from the accumulated state."""
    if final_state is None:
        return ""
    messages = final_state.get("messages", [])
    # Walk in reverse to find the last AIMessage with content and no tool calls
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
        if msg_type == "ai":
            content = getattr(msg, "content", "") or (msg.get("content", "") if isinstance(msg, dict) else "")
            tool_calls = getattr(msg, "tool_calls", []) or (msg.get("tool_calls", []) if isinstance(msg, dict) else [])
            if content and not tool_calls:
                return str(content)
    # No messages key — serialize the whole state
    if not messages:
        import json
        try:
            return json.dumps(final_state)
        except Exception:
            return str(final_state)
    return ""


def _push_event_nonblocking(
    execution_id: str,
    event: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget HTTP POST to /api/agent/events/{executionId}."""
    def _do_push():
        try:
            import requests
            url = f"{server_url}/api/agent/events/{execution_id}"
            headers = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (execution_id=%s): %s", execution_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)
```

- [ ] **Step 4: Run tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_langgraph_worker.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Run full unit suite**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

Expected: no regressions.

- [ ] **Step 6: Format and lint**

```bash
cd sdk/python && uv run ruff format src/agentspan/agents/frameworks/langgraph.py && \
  uv run ruff check src/agentspan/agents/frameworks/langgraph.py
```

- [ ] **Step 7: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/langgraph.py \
        sdk/python/tests/unit/test_langgraph_worker.py
git commit -m "feat(python): add LangGraph passthrough worker"
```

---

### Task 8: `frameworks/langchain.py`

**Files:**
- Create: `sdk/python/src/agentspan/agents/frameworks/langchain.py`
- Create: `sdk/python/tests/unit/test_langchain_worker.py`

**Context:** LangChain `AgentExecutor.invoke()` is synchronous. Streaming is via a `BaseCallbackHandler` injected as `callbacks=[handler]`. Input is always `{"input": prompt}`, output is `result["output"]`.

- [ ] **Step 1: Write failing unit tests**

```python
# sdk/python/tests/unit/test_langchain_worker.py
"""Unit tests for the LangChain passthrough worker."""
from unittest.mock import MagicMock, patch


def _make_executor(output="answer"):
    executor = MagicMock()
    type(executor).__name__ = "AgentExecutor"
    executor.invoke.return_value = {"output": output}
    return executor


def _make_task(prompt="Hello", session_id="", execution_id="wf-456"):
    from conductor.client.http.models.task import Task
    task = MagicMock(spec=Task)
    task.input_data = {"prompt": prompt, "session_id": session_id}
    task.workflow_instance_id = execution_id
    return task


class TestSerializeLangchain:
    def test_returns_single_worker_info(self):
        from agentspan.agents.frameworks.langchain import serialize_langchain
        executor = _make_executor()
        executor.name = "my_executor"

        raw_config, workers = serialize_langchain(executor)

        assert len(workers) == 1
        assert workers[0].name == "my_executor"

    def test_raw_config_has_name_and_worker_name(self):
        from agentspan.agents.frameworks.langchain import serialize_langchain
        executor = _make_executor()
        executor.name = "my_executor"

        raw_config, _ = serialize_langchain(executor)

        assert raw_config["name"] == "my_executor"
        assert raw_config["_worker_name"] == "my_executor"


class TestMakeLangchainWorker:
    def test_worker_returns_executor_output(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        executor = _make_executor(output="The answer is 42")
        task = _make_task(prompt="What is the answer?")

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                executor, "my_executor", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "The answer is 42"

    def test_worker_passes_prompt_as_input(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        executor = _make_executor()
        task = _make_task(prompt="search for python")

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                executor, "my_executor", "http://localhost:6767", "key", "secret"
            )
            worker_fn(task)

        call_args = executor.invoke.call_args
        assert call_args[0][0]["input"] == "search for python"

    def test_worker_returns_failed_on_exception(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        executor = _make_executor()
        executor.invoke.side_effect = RuntimeError("tool error")
        task = _make_task()

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                executor, "my_executor", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "tool error" in result.reason_for_incompletion

    def test_worker_pushes_tool_call_event_via_callback(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker, AgentspanCallbackHandler

        executor = _make_executor()
        task = _make_task(execution_id="wf-push-test")

        pushed_events = []

        def fake_push(wf_id, event, *args):
            pushed_events.append(event)

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking", side_effect=fake_push):
            # Simulate callback being triggered
            handler = AgentspanCallbackHandler("wf-push-test", "http://localhost:6767", "k", "s")
            handler.on_tool_start({"name": "search"}, "python", run_id=None)
            handler.on_tool_end("result text", run_id=None)

        tool_calls = [e for e in pushed_events if e["type"] == "tool_call"]
        tool_results = [e for e in pushed_events if e["type"] == "tool_result"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["toolName"] == "search"
        assert len(tool_results) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk/python && uv run pytest tests/unit/test_langchain_worker.py -v 2>&1 | tail -20
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `frameworks/langchain.py`**

```python
# sdk/python/src/agentspan/agents/frameworks/langchain.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangChain AgentExecutor passthrough worker support."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.langchain")

_EVENT_PUSH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langchain-event-push")
_DEFAULT_NAME = "langchain_agent"


def serialize_langchain(executor: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a LangChain AgentExecutor into (raw_config, [WorkerInfo])."""
    name = getattr(executor, "name", None) or _DEFAULT_NAME
    raw_config = {"name": name, "_worker_name": name}

    worker = WorkerInfo(
        name=name,
        description=f"LangChain passthrough worker for {name}",
        input_schema={"type": "object", "properties": {
            "prompt": {"type": "string"},
            "session_id": {"type": "string"},
        }},
        func=None,  # placeholder — replaced at registration time
    )
    return raw_config, [worker]


def make_langchain_worker(
    executor: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Any:
    """Build a pre-wrapped tool_worker(task) -> TaskResult for a LangChain AgentExecutor."""
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def tool_worker(task: Task) -> TaskResult:
        execution_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")

        try:
            handler = AgentspanCallbackHandler(execution_id, server_url, auth_key, auth_secret)
            result = executor.invoke({"input": prompt}, config={"callbacks": [handler]})
            output = result.get("output", "") if isinstance(result, dict) else str(result)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"result": output},
            )
        except Exception as exc:
            logger.error("LangChain worker error (execution_id=%s): %s", execution_id, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )

    return tool_worker


class AgentspanCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that pushes events to Agentspan SSE via HTTP.

    Must inherit from BaseCallbackHandler so LangChain's AgentExecutor
    recognises it as a valid callback. Plain classes are rejected at runtime.
    """

    def __init__(self, execution_id: str, server_url: str, auth_key: str, auth_secret: str):
        super().__init__()
        self._execution_id = execution_id
        self._server_url = server_url
        self._auth_key = auth_key
        self._auth_secret = auth_secret
        self._current_tool_name: Optional[str] = None

    def on_llm_start(self, serialized, prompts, **kwargs):
        _push_event_nonblocking(
            self._execution_id,
            {"type": "thinking", "content": "llm"},
            self._server_url, self._auth_key, self._auth_secret,
        )

    def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "") if isinstance(serialized, dict) else ""
        self._current_tool_name = tool_name
        _push_event_nonblocking(
            self._execution_id,
            {"type": "tool_call", "toolName": tool_name, "args": {"input": input_str}},
            self._server_url, self._auth_key, self._auth_secret,
        )

    def on_tool_end(self, output, **kwargs):
        _push_event_nonblocking(
            self._execution_id,
            {"type": "tool_result", "toolName": self._current_tool_name or "", "result": str(output)},
            self._server_url, self._auth_key, self._auth_secret,
        )
        self._current_tool_name = None

    def on_tool_error(self, error, **kwargs):
        _push_event_nonblocking(
            self._execution_id,
            {"type": "tool_result", "toolName": self._current_tool_name or "", "result": f"ERROR: {error}"},
            self._server_url, self._auth_key, self._auth_secret,
        )
        self._current_tool_name = None


def _push_event_nonblocking(
    execution_id: str,
    event: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget HTTP POST to /api/agent/events/{executionId}."""
    def _do_push():
        try:
            import requests
            url = f"{server_url}/api/agent/events/{execution_id}"
            headers = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (execution_id=%s): %s", execution_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)
```

- [ ] **Step 4: Run tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_langchain_worker.py -v 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 5: Format and lint**

```bash
cd sdk/python && uv run ruff format src/agentspan/agents/frameworks/langchain.py && \
  uv run ruff check src/agentspan/agents/frameworks/langchain.py
```

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/langchain.py \
        sdk/python/tests/unit/test_langchain_worker.py
git commit -m "feat(python): add LangChain passthrough worker"
```

---

### Task 9: Wire `serialize_agent()` and `runtime.py` registration

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/serializer.py`
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py`
- Create: `sdk/python/tests/unit/test_passthrough_registration.py`

- [ ] **Step 1: Write failing tests**

```python
# sdk/python/tests/unit/test_passthrough_registration.py
"""Tests for passthrough worker registration path in runtime.py."""
from unittest.mock import MagicMock, patch, call


def _make_graph():
    graph = MagicMock()
    type(graph).__name__ = "CompiledStateGraph"
    graph.name = "test_graph"
    return graph


class TestSerializeAgentDispatching:
    def test_langgraph_dispatches_to_serialize_langgraph(self):
        from agentspan.agents.frameworks.serializer import serialize_agent

        graph = _make_graph()

        with patch("agentspan.agents.frameworks.langgraph.serialize_langgraph") as mock_serialize:
            mock_serialize.return_value = ({"name": "test_graph"}, [])
            serialize_agent(graph)
            mock_serialize.assert_called_once_with(graph)

    def test_langchain_dispatches_to_serialize_langchain(self):
        from agentspan.agents.frameworks.serializer import serialize_agent

        executor = MagicMock()
        type(executor).__name__ = "AgentExecutor"

        with patch("agentspan.agents.frameworks.langchain.serialize_langchain") as mock_serialize:
            mock_serialize.return_value = ({"name": "my_exec"}, [])
            serialize_agent(executor)
            mock_serialize.assert_called_once_with(executor)


class TestPassthroughTaskDef:
    def test_passthrough_task_def_has_600s_timeout(self):
        from agentspan.agents.runtime.runtime import _passthrough_task_def

        td = _passthrough_task_def("my_graph")

        assert td.timeout_seconds == 600
        assert td.response_timeout_seconds == 600
        assert td.name == "my_graph"


class TestSerializeAgentFuncPlaceholder:
    def test_serialize_langgraph_returns_func_none_placeholder(self):
        """serialize_langgraph returns func=None; _build_passthrough_func fills it later.
        This test documents the design: serialize_agent() is only called for rawConfig,
        and _build_passthrough_func() provides the actual pre-wrapped worker func.
        """
        from agentspan.agents.frameworks.serializer import serialize_agent

        graph = MagicMock()
        type(graph).__name__ = "CompiledStateGraph"
        graph.name = "test_graph"

        with patch("agentspan.agents.frameworks.langgraph.serialize_langgraph") as mock_sl:
            mock_sl.return_value = ({"name": "test_graph"}, [
                MagicMock(name="test_graph", func=None)
            ])
            _, workers = serialize_agent(graph)

        # func=None is expected here — it is a placeholder
        assert workers[0].func is None  # filled by _build_passthrough_func before registration
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk/python && uv run pytest tests/unit/test_passthrough_registration.py -v 2>&1 | tail -20
```

Expected: FAIL.

- [ ] **Step 3: Update `serialize_agent()` in `serializer.py`**

At the top of `serialize_agent()` (line 64), insert framework dispatch **before** the existing `workers: List[WorkerInfo] = []` line. The existing function body is unchanged after that point.

Replace the function docstring + first line only (insert 7 lines, don't touch the rest):

```python
def serialize_agent(agent_obj: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Generic deep serialization of any agent object.

    For LangGraph and LangChain, dispatches to framework-specific serializers
    that return a pre-wrapped passthrough worker (func=None placeholder).
    For OpenAI and Google ADK, uses deep serialization with callable extraction.
    """
    # LangGraph/LangChain: short-circuit to framework-specific serializer
    # Note: func=None in returned WorkerInfo — filled by _build_passthrough_func()
    # in runtime._start_framework() before calling _register_passthrough_worker().
    framework = detect_framework(agent_obj)
    if framework == "langgraph":
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        return serialize_langgraph(agent_obj)
    if framework == "langchain":
        from agentspan.agents.frameworks.langchain import serialize_langchain
        return serialize_langchain(agent_obj)

    # --- Everything below is the original function body, unchanged ---
    workers: List[WorkerInfo] = []
    seen: Set[int] = set()
    # ... (rest of existing function unchanged)
```

> **Precise edit**: Use the Edit tool to target the existing docstring and the `workers: List[WorkerInfo] = []` line (line 74) as the `old_string` anchor point. Add the 7 dispatch lines between the docstring close and the `workers` line.

- [ ] **Step 4: Add `_passthrough_task_def()` to `runtime.py`**

After the existing `_default_task_def()` function (around line 56), add:

```python
def _passthrough_task_def(name: str) -> Any:
    """Create a TaskDef with extended timeout for framework passthrough workers.

    LangGraph/LangChain graphs can run much longer than the 120s default.
    """
    from conductor.client.http.models.task_def import TaskDef

    td = TaskDef(name=name)
    td.retry_count = 2
    td.retry_logic = "LINEAR_BACKOFF"
    td.retry_delay_seconds = 2
    td.timeout_seconds = 600
    td.response_timeout_seconds = 600
    td.timeout_policy = "RETRY"
    return td
```

- [ ] **Step 5: Add `_register_passthrough_worker()` to `runtime.py`**

After `_register_framework_workers()` (around line 2379), add:

```python
def _register_passthrough_worker(self, worker: Any) -> None:
    """Register a pre-wrapped framework passthrough worker (LangGraph/LangChain).

    Unlike _register_framework_workers, this does NOT call make_tool_worker —
    worker.func is already a pre-wrapped tool_worker(task) -> TaskResult closure.
    Uses _passthrough_task_def (600s timeout) instead of _default_task_def (120s).
    """
    from conductor.client.worker.worker_task import worker_task

    # Add minimal annotations so the Conductor SDK can introspect the function
    worker.func.__annotations__ = {"task": object, "return": object}

    worker_task(
        task_definition_name=worker.name,
        task_def=_passthrough_task_def(worker.name),
        register_task_def=True,
        overwrite_task_def=True,
    )(worker.func)
    logger.debug("Registered passthrough worker '%s'", worker.name)

    if self._config.auto_start_workers:
        with self._worker_start_lock:
            is_new = worker.name not in self._registered_tool_names
            if is_new:
                self._registered_tool_names.add(worker.name)
            if not self._workers_started:
                logger.debug("Starting workers for passthrough worker '%s'", worker.name)
                self._worker_manager.start()
                self._workers_started = True
            elif is_new:
                self._worker_manager.start()
```

- [ ] **Step 6: Update `_start_framework()` to branch on framework ID**

In `_start_framework()` (around line 2275), replace the current single-path `serialize_agent` + `_register_framework_workers` with branching:

Current code (~line 2286-2289):
```python
raw_config, workers = serialize_agent(agent_obj)
self._register_framework_workers(workers)
```

Replace with:
```python
raw_config, workers = serialize_agent(agent_obj)

if framework in ("langgraph", "langchain"):
    # Build the actual pre-wrapped worker function with server connection info
    # (func was None from serialize_langgraph/serialize_langchain — fill it now)
    worker = workers[0]
    worker.func = self._build_passthrough_func(agent_obj, framework, worker.name)
    self._register_passthrough_worker(worker)
else:
    self._register_framework_workers(workers)
```

- [ ] **Step 7: Add `_build_passthrough_func()` helper to `runtime.py`**

```python
def _build_passthrough_func(self, agent_obj: Any, framework: str, name: str) -> Any:
    """Build the pre-wrapped tool_worker function for a passthrough worker."""
    server_url = self._config.server_url
    auth_key = self._config.key_id or ""
    auth_secret = self._config.key_secret or ""

    if framework == "langgraph":
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker
        return make_langgraph_worker(agent_obj, name, server_url, auth_key, auth_secret)
    elif framework == "langchain":
        from agentspan.agents.frameworks.langchain import make_langchain_worker
        return make_langchain_worker(agent_obj, name, server_url, auth_key, auth_secret)
    raise ValueError(f"Unknown passthrough framework: {framework}")
```

> Also apply the same branching to `_start_framework_async()` if it exists (check around line 3583 in runtime.py).

- [ ] **Step 8: Run tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_passthrough_registration.py -v 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 9: Run full unit suite**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

Expected: no regressions.

- [ ] **Step 10: Format and lint**

```bash
cd sdk/python && uv run ruff format src/agentspan/agents/frameworks/serializer.py \
  src/agentspan/agents/runtime/runtime.py && \
  uv run ruff check src/agentspan/agents/frameworks/serializer.py \
  src/agentspan/agents/runtime/runtime.py
```

- [ ] **Step 11: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/serializer.py \
        sdk/python/src/agentspan/agents/runtime/runtime.py \
        sdk/python/tests/unit/test_passthrough_registration.py
git commit -m "feat(python): wire passthrough registration path in runtime and serializer"
```

---

## Chunk 3: Example 1 — LangGraph ReAct Agent (TDD)

**Goal:** Prove the full end-to-end pipeline works with `create_react_agent` + tools.

**Prerequisites:** langgraph and langchain-core must be installed:
```bash
cd sdk/python && uv add --dev langgraph langchain-core langchain-openai
```

### Task 10: Integration test for LangGraph ReAct agent

**Files:**
- Create: `sdk/python/tests/unit/test_langgraph_react_example.py`

This test runs without a real server — it mocks the Conductor client and HTTP push, but exercises the real `create_react_agent` graph creation and worker invocation logic.

- [ ] **Step 1: Write the failing integration-style unit test**

```python
# sdk/python/tests/unit/test_langgraph_react_example.py
"""
Example 1: LangGraph ReAct agent.
Verifies that a graph built with create_react_agent can be:
1. Detected as "langgraph" framework
2. Serialized to (raw_config, [WorkerInfo])
3. Invoked via the pre-wrapped worker function with correct output extraction
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def react_graph():
    """Build a real create_react_agent graph with a mocked LLM."""
    pytest.importorskip("langgraph")
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import AIMessage

    # Mock LLM that always returns a plain text response (no tool calls)
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="The capital is Paris.")
    llm.bind_tools = lambda tools: llm  # bind_tools returns itself

    # Simple tool
    from langchain_core.tools import tool

    @tool
    def get_capital(country: str) -> str:
        """Get the capital of a country."""
        return f"The capital of {country} is Paris."

    graph = create_react_agent(llm, tools=[get_capital])
    return graph


class TestLangGraphReActDetection:
    def test_detect_framework_returns_langgraph(self, react_graph):
        from agentspan.agents.frameworks.serializer import detect_framework
        assert detect_framework(react_graph) == "langgraph"

    def test_serialize_returns_single_worker(self, react_graph):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        raw_config, workers = serialize_langgraph(react_graph)
        assert len(workers) == 1

    def test_worker_invocation_extracts_ai_message_output(self, react_graph):
        from langchain_core.messages import HumanMessage, AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        # Patch the graph's stream to return controlled output
        final_ai_msg = AIMessage(content="The capital is Paris.", tool_calls=[])
        final_ai_msg.type = "ai"

        stream_chunks = [
            ("updates", {"agent": {"messages": [final_ai_msg]}}),
            ("values", {"messages": [
                HumanMessage(content="What is the capital of France?"),
                final_ai_msg,
            ]}),
        ]

        task = MagicMock()
        task.task_id = "t-1"
        task.workflow_instance_id = "wf-react-1"
        task.input_data = {"prompt": "What is the capital of France?", "session_id": ""}

        with patch.object(react_graph, "stream", return_value=iter(stream_chunks)):
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    react_graph, "react_agent", "http://localhost:6767", "key", "secret"
                )
                result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "The capital is Paris."

    def test_worker_uses_messages_input_format(self, react_graph):
        """create_react_agent graphs use messages-based state."""
        from langchain_core.messages import HumanMessage, AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        final_msg = AIMessage(content="Done.", tool_calls=[])
        final_msg.type = "ai"
        stream_chunks = [
            ("updates", {"agent": {"messages": [final_msg]}}),
            ("values", {"messages": [final_msg]}),
        ]

        task = MagicMock()
        task.task_id = "t-2"
        task.workflow_instance_id = "wf-react-2"
        task.input_data = {"prompt": "Hello", "session_id": ""}

        with patch.object(react_graph, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    react_graph, "react_agent", "http://localhost:6767", "key", "secret"
                )
                worker_fn(task)

        # Verify the input to stream() has messages key with HumanMessage
        input_arg = mock_stream.call_args[0][0]
        assert "messages" in input_arg
        assert isinstance(input_arg["messages"][0], HumanMessage)
        assert input_arg["messages"][0].content == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/test_langgraph_react_example.py -v 2>&1 | tail -30
```

Expected: `ModuleNotFoundError` for `langgraph` (if not installed) or actual test failures.

- [ ] **Step 3: Verify dev dependencies are installed** (should already be from Chunk 2 prerequisite)

```bash
cd sdk/python && uv run python3 -c "import langgraph; import langchain_core; print('OK')"
```

- [ ] **Step 4: Run tests again**

```bash
cd sdk/python && uv run pytest tests/unit/test_langgraph_react_example.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Run full unit suite to check no regressions**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

- [ ] **Step 6: Commit**

```bash
git add sdk/python/tests/unit/test_langgraph_react_example.py \
        sdk/python/pyproject.toml sdk/python/uv.lock
git commit -m "test(python): add LangGraph ReAct agent example tests"
```

---

## Chunk 4: Example 2 — LangGraph Custom StateGraph

**Goal:** Verify non-messages state schemas (custom `TypedDict` state) work with auto-detected input/output.

### Task 11: Custom StateGraph example test

**Files:**
- Create: `sdk/python/tests/unit/test_langgraph_stategraph_example.py`

- [ ] **Step 1: Write failing test**

```python
# sdk/python/tests/unit/test_langgraph_stategraph_example.py
"""
Example 2: LangGraph custom StateGraph with non-messages state.
Verifies auto-detection of non-messages input/output schemas.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def custom_graph():
    """Build a simple StateGraph with a custom state schema (no messages)."""
    pytest.importorskip("langgraph")
    from typing import TypedDict
    from langgraph.graph import StateGraph, END

    class State(TypedDict):
        query: str
        answer: str

    def process(state: State) -> State:
        return {"answer": f"Answer to: {state['query']}"}

    builder = StateGraph(State)
    builder.add_node("process", process)
    builder.set_entry_point("process")
    builder.add_edge("process", END)
    return builder.compile()


class TestCustomStateGraph:
    def test_detect_framework(self, custom_graph):
        from agentspan.agents.frameworks.serializer import detect_framework
        assert detect_framework(custom_graph) == "langgraph"

    def test_worker_extracts_non_messages_output_as_json(self, custom_graph):
        """When state has no messages key, output is JSON of the state dict."""
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker
        import json

        stream_chunks = [
            ("updates", {"process": {"answer": "Answer to: hello"}}),
            ("values", {"query": "hello", "answer": "Answer to: hello"}),
        ]

        task = MagicMock()
        task.task_id = "t-custom"
        task.workflow_instance_id = "wf-custom-1"
        task.input_data = {"prompt": "hello", "session_id": ""}

        with patch.object(custom_graph, "stream", return_value=iter(stream_chunks)):
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    custom_graph, "custom_graph", "http://localhost:6767", "k", "s"
                )
                result = worker_fn(task)

        assert result.status == "COMPLETED"
        # Output should be JSON of the state since there are no messages
        output = json.loads(result.output_data["result"])
        assert output["answer"] == "Answer to: hello"

    def test_worker_uses_first_required_string_property_as_input_key(self, custom_graph):
        """Non-messages graph: input key = first required string property."""
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        stream_chunks = [
            ("updates", {"process": {"answer": "done"}}),
            ("values", {"query": "test prompt", "answer": "done"}),
        ]

        task = MagicMock()
        task.task_id = "t-input"
        task.workflow_instance_id = "wf-input-1"
        task.input_data = {"prompt": "test prompt", "session_id": ""}

        with patch.object(custom_graph, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    custom_graph, "custom_graph", "http://localhost:6767", "k", "s"
                )
                worker_fn(task)

        input_arg = mock_stream.call_args[0][0]
        # "query" is the first required string property in State schema
        assert "query" in input_arg
        assert input_arg["query"] == "test prompt"
```

- [ ] **Step 2: Run test**

```bash
cd sdk/python && uv run pytest tests/unit/test_langgraph_stategraph_example.py -v 2>&1 | tail -30
```

- [ ] **Step 3: Fix any failures in `_build_input()` logic**

If the `test_worker_uses_first_required_string_property_as_input_key` test fails, the `_build_input()` function in `langgraph.py` needs adjustment. The `get_input_jsonschema()` for a `StateGraph(State)` where `State` has `query: str` should return the `query` key as a required string property.

Debug what schema the graph actually returns:
```bash
cd sdk/python && uv run python3 -c "
from typing import TypedDict
from langgraph.graph import StateGraph, END
class State(TypedDict):
    query: str
    answer: str
def p(s): return {'answer': 'x'}
b = StateGraph(State)
b.add_node('process', p)
b.set_entry_point('process')
b.add_edge('process', END)
g = b.compile()
import json; print(json.dumps(g.get_input_jsonschema(), indent=2))
"
```

Adjust `_build_input()` accordingly.

- [ ] **Step 4: Run all unit tests**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add sdk/python/tests/unit/test_langgraph_stategraph_example.py \
        sdk/python/src/agentspan/agents/frameworks/langgraph.py
git commit -m "test(python): add custom StateGraph example; fix non-messages output extraction"
```

---

## Chunk 5: Example 3 — LangGraph with Checkpointer

**Goal:** Verify `session_id` → `thread_id` mapping for conversation continuity.

### Task 12: Checkpointer example test

**Files:**
- Create: `sdk/python/tests/unit/test_langgraph_checkpointer_example.py`

- [ ] **Step 1: Write failing test**

```python
# sdk/python/tests/unit/test_langgraph_checkpointer_example.py
"""
Example 3: LangGraph with MemorySaver checkpointer.
Verifies session_id -> thread_id mapping for multi-turn conversation.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def graph_with_checkpointer():
    pytest.importorskip("langgraph")
    from langgraph.prebuilt import create_react_agent
    from langgraph.checkpoint.memory import MemorySaver
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="Hello!")
    llm.bind_tools = lambda tools: llm

    memory = MemorySaver()
    graph = create_react_agent(llm, tools=[], checkpointer=memory)
    return graph


class TestCheckpointerSupport:
    def test_session_id_is_passed_as_thread_id(self, graph_with_checkpointer):
        from langchain_core.messages import AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        ai_msg = AIMessage(content="Hello!", tool_calls=[])
        ai_msg.type = "ai"
        stream_chunks = [
            ("updates", {"agent": {"messages": [ai_msg]}}),
            ("values", {"messages": [ai_msg]}),
        ]

        task = MagicMock()
        task.task_id = "t-ckpt"
        task.workflow_instance_id = "wf-ckpt-1"
        task.input_data = {"prompt": "Hi", "session_id": "user-session-abc"}

        with patch.object(graph_with_checkpointer, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    graph_with_checkpointer, "memory_graph", "http://localhost:6767", "k", "s"
                )
                worker_fn(task)

        config_arg = mock_stream.call_args[0][1]
        assert config_arg["configurable"]["thread_id"] == "user-session-abc"

    def test_empty_session_id_passes_no_config(self, graph_with_checkpointer):
        from langchain_core.messages import AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        ai_msg = AIMessage(content="Hello!", tool_calls=[])
        ai_msg.type = "ai"
        stream_chunks = [
            ("updates", {"agent": {"messages": [ai_msg]}}),
            ("values", {"messages": [ai_msg]}),
        ]

        task = MagicMock()
        task.task_id = "t-no-session"
        task.workflow_instance_id = "wf-no-session"
        task.input_data = {"prompt": "Hi", "session_id": ""}

        with patch.object(graph_with_checkpointer, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    graph_with_checkpointer, "memory_graph", "http://localhost:6767", "k", "s"
                )
                worker_fn(task)

        config_arg = mock_stream.call_args[0][1]
        # Empty session_id -> empty config dict (no configurable.thread_id)
        assert "configurable" not in config_arg

    def test_checkpointer_error_returns_failed_result(self, graph_with_checkpointer):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph_with_checkpointer.stream = MagicMock(
            side_effect=ValueError("No checkpointer configured")
        )

        task = MagicMock()
        task.task_id = "t-err"
        task.workflow_instance_id = "wf-err"
        task.input_data = {"prompt": "Hi", "session_id": "s-1"}

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph_with_checkpointer, "memory_graph", "http://localhost:6767", "k", "s"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "checkpointer" in result.reason_for_incompletion.lower()
```

- [ ] **Step 2: Run test**

```bash
cd sdk/python && uv run pytest tests/unit/test_langgraph_checkpointer_example.py -v 2>&1 | tail -30
```

Expected: all tests pass (the config logic was already implemented in Task 7).

- [ ] **Step 3: Commit**

```bash
git add sdk/python/tests/unit/test_langgraph_checkpointer_example.py
git commit -m "test(python): add LangGraph checkpointer / session_id example tests"
```

---

## Chunk 6: Example 4 — LangChain AgentExecutor

**Goal:** Verify `AgentExecutor` with tools works end-to-end with streaming callbacks.

### Task 13: LangChain AgentExecutor example test

**Files:**
- Create: `sdk/python/tests/unit/test_langchain_executor_example.py`

- [ ] **Step 1: Write failing test**

```python
# sdk/python/tests/unit/test_langchain_executor_example.py
"""
Example 4: LangChain AgentExecutor.
Verifies full pipeline from executor creation through worker invocation.
"""
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def agent_executor():
    """Build a minimal AgentExecutor-like object (mock with real type name)."""
    pytest.importorskip("langchain")
    from langchain.agents import AgentExecutor

    # Create a real AgentExecutor with mocked agent and tools
    agent = MagicMock()
    executor = MagicMock(spec=AgentExecutor)
    type(executor).__name__ = "AgentExecutor"
    executor.invoke.return_value = {"output": "42"}
    executor.name = "math_executor"
    return executor


class TestLangChainExecutorDetection:
    def test_detect_framework_returns_langchain(self, agent_executor):
        from agentspan.agents.frameworks.serializer import detect_framework
        assert detect_framework(agent_executor) == "langchain"

    def test_serialize_returns_single_worker(self, agent_executor):
        from agentspan.agents.frameworks.langchain import serialize_langchain
        raw_config, workers = serialize_langchain(agent_executor)
        assert len(workers) == 1
        assert raw_config["name"] == "math_executor"


class TestLangChainWorkerInvocation:
    def test_worker_returns_executor_output(self, agent_executor):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        task = MagicMock()
        task.task_id = "t-lc"
        task.workflow_instance_id = "wf-lc-1"
        task.input_data = {"prompt": "What is 6*7?", "session_id": ""}

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                agent_executor, "math_executor", "http://localhost:6767", "k", "s"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "42"

    def test_worker_injects_callback_handler(self, agent_executor):
        """Verify that AgentspanCallbackHandler is passed to executor.invoke."""
        from agentspan.agents.frameworks.langchain import make_langchain_worker, AgentspanCallbackHandler

        task = MagicMock()
        task.task_id = "t-cb"
        task.workflow_instance_id = "wf-cb-1"
        task.input_data = {"prompt": "test", "session_id": ""}

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                agent_executor, "math_executor", "http://localhost:6767", "k", "s"
            )
            worker_fn(task)

        invoke_call = agent_executor.invoke.call_args
        config = invoke_call[1].get("config") or invoke_call[0][1] if len(invoke_call[0]) > 1 else {}
        callbacks = config.get("callbacks", [])
        assert any(isinstance(cb, AgentspanCallbackHandler) for cb in callbacks)

    def test_callback_on_tool_start_pushes_event(self):
        """Callback pushes tool_call event on tool start."""
        from agentspan.agents.frameworks.langchain import AgentspanCallbackHandler

        pushed = []
        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking",
                   side_effect=lambda wf_id, event, *a: pushed.append(event)):
            handler = AgentspanCallbackHandler("wf-1", "http://localhost:6767", "k", "s")
            handler.on_tool_start({"name": "calculator"}, "6*7", run_id=None)

        assert len(pushed) == 1
        assert pushed[0]["type"] == "tool_call"
        assert pushed[0]["toolName"] == "calculator"

    def test_callback_on_tool_end_pushes_event(self):
        from agentspan.agents.frameworks.langchain import AgentspanCallbackHandler

        pushed = []
        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking",
                   side_effect=lambda wf_id, event, *a: pushed.append(event)):
            handler = AgentspanCallbackHandler("wf-1", "http://localhost:6767", "k", "s")
            handler.on_tool_start({"name": "calculator"}, "6*7", run_id=None)
            handler.on_tool_end("42", run_id=None)

        results = [e for e in pushed if e["type"] == "tool_result"]
        assert len(results) == 1
        assert results[0]["result"] == "42"
```

- [ ] **Step 3: Run tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_langchain_executor_example.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 4: Run full unit suite**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/tests/unit/test_langchain_executor_example.py \
        sdk/python/pyproject.toml sdk/python/uv.lock
git commit -m "test(python): add LangChain AgentExecutor example tests"
```

---

## Final Verification

- [ ] **Run full Java test suite**

```bash
cd server && ./gradlew test -q 2>&1 | tail -20
```

Expected: BUILD SUCCESS.

- [ ] **Run full Python unit suite**

```bash
cd sdk/python && uv run pytest tests/unit/ -q 2>&1 | tail -20
```

Expected: all passing.

- [ ] **Smoke test: verify framework detection for both new frameworks**

```bash
cd sdk/python && uv run python3 -c "
from agentspan.agents.frameworks.serializer import detect_framework
from unittest.mock import MagicMock

# LangGraph
lg = MagicMock(); type(lg).__name__ = 'CompiledStateGraph'
print('LangGraph:', detect_framework(lg))  # should print: langgraph

# LangChain
lc = MagicMock(); type(lc).__name__ = 'AgentExecutor'
print('LangChain:', detect_framework(lc))  # should print: langchain

# Unknown
u = MagicMock(); type(u).__name__ = 'SomethingElse'; type(u).__module__ = 'other'
print('Unknown:', detect_framework(u))  # should print: None
"
```

- [ ] **Commit final verification**

```bash
git tag -a "langgraph-langchain-support" -m "LangGraph and LangChain support complete"
```
