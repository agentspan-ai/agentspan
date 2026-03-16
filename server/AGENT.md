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
| `org.openagent.runtime.compiler` | AgentConfig → Conductor WorkflowDef compilation |
| `org.openagent.runtime.controller` | REST API endpoints (`/api/agent/*`) |
| `org.openagent.runtime.service` | Business logic, SSE streaming, event listening |
| `org.openagent.runtime.model` | DTOs: AgentConfig, AgentSSEEvent, StartRequest, etc. |
| `org.openagent.runtime.util` | Helpers: ModelParser, JavaScriptBuilder |

### SSE Streaming Architecture

The SSE system has three layers:

1. **AgentEventListener** — Implements Conductor's `TaskStatusListener` + `WorkflowStatusListener`. Translates Conductor task/workflow state changes into `AgentSSEEvent` DTOs.
2. **AgentStreamRegistry** — Manages per-workflow `SseEmitter` connections, event buffering (bounded, 200 events), reconnection replay via `Last-Event-ID`, sub-workflow alias forwarding, and heartbeats.
3. **AgentController** — Exposes `GET /api/agent/stream/{workflowId}` SSE endpoint.

**Event types:** `thinking`, `tool_call`, `tool_result`, `handoff`, `waiting`, `guardrail_pass`, `guardrail_fail`, `error`, `done`

### REST API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent` | Health check |
| POST | `/api/agent/compile` | Compile AgentConfig → WorkflowDef (no execution) |
| POST | `/api/agent/start` | Compile + register + execute |
| GET | `/api/agent/stream/{workflowId}` | SSE event stream |
| POST | `/api/agent/{workflowId}/respond` | HITL response |
| GET | `/api/agent/{workflowId}/status` | Polling fallback |

## Testing

### CRITICAL: All new features MUST have real E2E tests

Do NOT rely solely on mock-based unit tests. Every feature that involves HTTP endpoints or SSE streaming **must** include integration tests that boot the full Spring context and test over real HTTP.

### Running Tests

```bash
# All tests
./gradlew test

# Unit tests only (fast, no Spring context)
./gradlew test --tests "org.openagent.runtime.compiler.*" --tests "org.openagent.runtime.model.*"

# SSE unit tests
./gradlew test --tests "org.openagent.runtime.service.AgentStreamRegistryTest" \
               --tests "org.openagent.runtime.service.AgentEventListenerTest" \
               --tests "org.openagent.runtime.model.AgentSSEEventTest" \
               --tests "org.openagent.runtime.controller.AgentControllerSSETest"

# SSE E2E integration tests (boots full Spring Boot + Conductor + SQLite)
./gradlew test --tests "org.openagent.runtime.controller.AgentControllerSSEIntegrationTest"
```

### Test Structure

| File | Type | What it tests |
|---|---|---|
| `model/AgentSSEEventTest.java` | Unit | Event factory methods, JSON serialization, null exclusion |
| `model/AgentConfigTest.java` | Unit | JSON deserialization, nested agents |
| `service/AgentStreamRegistryTest.java` | Unit | Emitter registration, event buffering, alias forwarding, reconnection replay, buffer eviction, heartbeats, cleanup |
| `service/AgentEventListenerTest.java` | Unit (mocked) | Conductor callback → SSE event mapping for all task/workflow states |
| `controller/AgentControllerSSETest.java` | Unit (mocked) | Controller delegation, lifecycle |
| `controller/AgentControllerSSEIntegrationTest.java` | **E2E** | Real HTTP SSE over `@SpringBootTest(RANDOM_PORT)` — all event types, reconnection, sub-workflow aliases, multi-client, wire format |
| `compiler/AgentCompilerTest.java` | Unit | Single agent compilation |
| `compiler/MultiAgentCompilerTest.java` | Unit | Multi-agent strategies |
| `compiler/GuardrailCompilerTest.java` | Unit | Guardrail compilation |
| `compiler/ToolCompilerTest.java` | Unit | Tool compilation |
| `compiler/TerminationCompilerTest.java` | Unit | Termination condition compilation |

### Writing Tests

- **Unit tests:** No Spring context. Mock external dependencies. Place in the appropriate package under `src/test/java/org/openagent/runtime/`.
- **Integration tests:** Use `@SpringBootTest(classes = AgentRuntime.class, webEnvironment = RANDOM_PORT)` with `@ActiveProfiles("test")`. Test config at `src/test/resources/application-test.properties`.
- **SSE tests MUST be E2E:** Use real `HttpURLConnection` to open SSE streams. Verify wire format (`id:`, `event:`, `data:` fields), not just Java objects.
- Use AssertJ for assertions, Mockito for mocks, JUnit 5 for test lifecycle.

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

1. **All SSE unit tests pass:** `./gradlew test --tests "org.openagent.runtime.service.*" --tests "org.openagent.runtime.model.AgentSSEEventTest" --tests "org.openagent.runtime.controller.AgentControllerSSETest"`
2. **SSE E2E integration tests pass:** `./gradlew test --tests "org.openagent.runtime.controller.AgentControllerSSEIntegrationTest"`
3. **Compiler tests pass:** `./gradlew test --tests "org.openagent.runtime.compiler.*"`
4. If adding a new SSE event type, add it to both unit tests AND the E2E `sseDeliversAllEventTypes` test
5. If adding a new endpoint, add an E2E integration test for it
