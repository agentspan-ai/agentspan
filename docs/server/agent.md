# AGENT.md — Guide for AI Agents Working on the Runtime Server

This file provides context for AI coding agents working on the Agent Runtime server (Java/Spring Boot).

## Project Overview

The Agent Runtime is a self-contained Spring Boot server that embeds the Conductor workflow engine. It compiles `AgentConfig` JSON into Conductor workflows, executes them, and streams real-time events to clients via SSE (Server-Sent Events).

**Stack:** Java 21, Spring Boot 3.3.5, Conductor 3.22.1-rc1, Gradle 8.x
**Database:** SQLite (default) or PostgreSQL
**Entry point:** `org.conductoross.conductor.AgentRuntime`

## Architecture

### Key Packages

| Package | Purpose |
|---|---|
| `org.conductoross.conductor` | Spring Boot application entry point |
| `dev.agentspan.runtime.compiler` | AgentConfig → Conductor WorkflowDef compilation |
| `dev.agentspan.runtime.controller` | REST API endpoints (`/api/agent/*`) |
| `dev.agentspan.runtime.service` | Business logic, SSE streaming, event listening |
| `dev.agentspan.runtime.model` | DTOs: AgentConfig, AgentSSEEvent, StartRequest, etc. |
| `dev.agentspan.runtime.util` | Helpers: ModelParser, JavaScriptBuilder |

### SSE Streaming Architecture

The SSE system has three layers:

1. **AgentEventListener** — Implements Conductor's `TaskStatusListener` + `WorkflowStatusListener`. Translates Conductor task/workflow state changes into `AgentSSEEvent` DTOs.
2. **AgentStreamRegistry** — Manages per-workflow `SseEmitter` connections, event buffering (bounded, 200 events), reconnection replay via `Last-Event-ID`, sub-workflow alias forwarding, and heartbeats.
3. **AgentController** — Exposes `GET /api/agent/stream/{executionId}` SSE endpoint.

**Event types:** `thinking`, `tool_call`, `tool_result`, `handoff`, `waiting`, `guardrail_pass`, `guardrail_fail`, `error`, `done`

### REST API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent` | Health check |
| POST | `/api/agent/compile` | Compile AgentConfig → WorkflowDef (no execution) |
| POST | `/api/agent/start` | Compile + register + execute |
| GET | `/api/agent/stream/{executionId}` | SSE event stream |
| POST | `/api/agent/{executionId}/respond` | HITL response |
| GET | `/api/agent/{executionId}/status` | Polling fallback |

## Testing

### CRITICAL: Unit tests and integration tests alone are NOT enough

Do NOT rely solely on mock-based unit tests or even Spring Boot integration tests. Integration tests verify the HTTP layer but run with AI providers disabled and an in-memory SQLite database — they cannot catch bugs that only surface when a real agent runs end-to-end.

**Every new server-side feature MUST be verified by running a real example from `sdk/python/examples/`** (e.g. `uv run python examples/claude/01_hello_world.py`) against a live server. Confirm the feature works as expected by inspecting the Conductor UI or the workflow execution response.

Every feature that involves HTTP endpoints or SSE streaming **must also** include Spring Boot integration tests that boot the full Spring context and test over real HTTP — but these are in addition to, not a replacement for, running real examples.

### Running Tests

```bash
# All tests
./gradlew test

# Unit tests only (fast, no Spring context)
./gradlew test --tests "dev.agentspan.runtime.compiler.*" --tests "dev.agentspan.runtime.model.*"

# SSE unit tests
./gradlew test --tests "dev.agentspan.runtime.service.AgentStreamRegistryTest" \
               --tests "dev.agentspan.runtime.service.AgentEventListenerTest" \
               --tests "dev.agentspan.runtime.model.AgentSSEEventTest" \
               --tests "dev.agentspan.runtime.controller.AgentControllerSSETest"

# SSE E2E integration tests (boots full Spring Boot + Conductor + SQLite)
./gradlew test --tests "dev.agentspan.runtime.controller.AgentControllerSSEIntegrationTest"
```

### Test Structure

| File | Type | What it tests |
|---|---|---|
| `model/AgentSSEEventTest.java` | Unit | Event factory methods, JSON serialization, null exclusion |
| `model/AgentConfigTest.java` | Unit | JSON deserialization, nested agents |
| `service/AgentStreamRegistryTest.java` | Unit | Emitter registration, event buffering, alias forwarding, reconnection replay, buffer eviction, heartbeats, cleanup |
| `service/AgentEventListenerTest.java` | Unit | Conductor callback → SSE event mapping for all task/workflow states |
| `controller/AgentControllerSSETest.java` | Unit | Controller delegation, lifecycle |
| `controller/AgentControllerSSEIntegrationTest.java` | **E2E** | Real HTTP SSE over `@SpringBootTest(RANDOM_PORT)` — all event types, reconnection, sub-workflow aliases, multi-client, wire format |
| `compiler/AgentCompilerTest.java` | Unit | Single agent compilation |
| `compiler/MultiAgentCompilerTest.java` | Unit | Multi-agent strategies |
| `compiler/GuardrailCompilerTest.java` | Unit | Guardrail compilation |
| `compiler/ToolCompilerTest.java` | Unit | Tool compilation |
| `compiler/TerminationCompilerTest.java` | Unit | Termination condition compilation |

### Writing Tests

- **Do NOT use mocks (Mockito) for internal services.** Tests that mock `CredentialStoreProvider`, `CredentialBindingService`, `UserRepository`, `ExecutionTokenService`, or any other internal service hide bugs at layer boundaries — the exact place bugs live. Use `@SpringBootTest` with the test profile's real SQLite DB instead.
- **Mocks are only acceptable for external framework objects** that cannot be instantiated in tests (e.g., Conductor's `WorkflowExecutor`, servlet `HttpServletRequest`). If you can use the real implementation, use it.
- **Unit tests** (no Spring context) are for pure logic only: compilers, parsers, model serialization. Place in the appropriate package under `src/test/java/dev/agentspan/runtime/`.
- **Integration tests:** Use `@SpringBootTest(classes = AgentRuntime.class, webEnvironment = RANDOM_PORT)` with `@ActiveProfiles("test")`. Test config at `src/test/resources/application-test.properties`.
- **SSE tests MUST be E2E:** Use real `HttpURLConnection` to open SSE streams. Verify wire format (`id:`, `event:`, `data:` fields), not just Java objects.
- Use AssertJ for assertions, JUnit 5 for test lifecycle.
- **Real examples are mandatory:** After all automated tests pass, run a real agent example (`uv run python examples/claude/01_hello_world.py` from `sdk/python/`) against a live server to verify the feature end-to-end.

### Integration Test Config

`src/test/resources/application-test.properties` configures:
- In-memory SQLite (`:memory:`)
- Indexing via SQLite
- AI providers disabled
- Random server port

## Model Context Windows

The `ModelContextWindows` utility (`src/main/java/dev/agentspan/runtime/util/ModelContextWindows.java`) maps model names to context window sizes (tokens) for proactive context condensation. When adding new models or updating capacities, use these authoritative sources:

- **OpenAI:** https://developers.openai.com/api/docs/models
- **Anthropic Claude:** https://platform.claude.com/docs/en/about-claude/models/overview
- **Google Gemini:** https://ai.google.dev/gemini-api/docs/models

Update the static defaults in `ModelContextWindows.java`. Users can also override at runtime via application properties or env vars — see `application.properties`.

## Validation Checklist

Before merging any change:

1. **All SSE unit tests pass:** `./gradlew test --tests "dev.agentspan.runtime.service.*" --tests "dev.agentspan.runtime.model.AgentSSEEventTest" --tests "dev.agentspan.runtime.controller.AgentControllerSSETest"`
2. **SSE E2E integration tests pass:** `./gradlew test --tests "dev.agentspan.runtime.controller.AgentControllerSSEIntegrationTest"`
3. **Compiler tests pass:** `./gradlew test --tests "dev.agentspan.runtime.compiler.*"`
4. **Full test suite passes:** `./gradlew test`
5. **Run a real example end-to-end:** `cd sdk/python && uv run python examples/claude/01_hello_world.py` against a live server. Confirm the feature works by inspecting the Conductor UI or workflow execution response. **This step is mandatory — automated tests cannot catch bugs that require a real running agent.**
6. If adding a new SSE event type, add it to both unit tests AND the E2E `sseDeliversAllEventTypes` test
7. If adding a new endpoint, add an E2E integration test for it AND verify with a real example run
