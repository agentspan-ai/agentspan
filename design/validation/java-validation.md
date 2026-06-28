# Java SDK — Validation & E2E

**Status:** Created 2026-06-26

**Scope:** How the Java SDK is validated end-to-end. Unlike the Python and TypeScript SDKs — which add a TOML-driven, LLM-judged *examples-quality* validation framework on top of their deterministic suites — **Java validation is the deterministic e2e suite only**: a set of JUnit 5 `@Tag("e2e")` test classes under `sdk/java/e2e/`, run against a live Agentspan server, locally and in CI. There is **no** separate examples-quality / LLM-judge harness for Java. Per `CLAUDE.md`, the e2e suites are deterministic: assertions are on compiled-workflow JSON structure, workflow task status, or in-process side effects (e.g. an `AtomicBoolean`/`AtomicReference` set inside a tool body) — never on LLM output text, except where the task is itself an eval.

Related:
- Methodology / framework spec: [`README.md`](README.md) (Python-centric; the LLM-judge orchestrator described there does **not** apply to Java)
- Java implementation design: [`../sdk-design/languages/java-implementation.md`](../sdk-design/languages/java-implementation.md)
- Cross-SDK design: [`../sdk-design.md`](../sdk-design.md)

---

## 1. Overview

Java validation = **deterministic e2e suites**, run locally and in CI against a real server with real LLM calls. No mocks. The principle (shared with the other SDKs): exercise real agents through the real server, but make every *assertion* deterministic so a green run actually proves something.

Three deterministic assertion shapes are used across the suites:
- **Plan-level (no LLM):** call `runtime.plan()` / `/agent/compile`, then assert on the compiled Conductor `workflowDef` / `agentDef` JSON. Pure structure checks (serialization round-trips, injected worker tools, sub-workflow shape).
- **Runtime side-effect:** run a real agent, but assert on a side effect captured inside the tool body (`AtomicBoolean` flag, `AtomicReference` captured argument). The LLM drives the agent; the recorded side effect is the signal.
- **Runtime workflow-status:** run a real agent and assert on server-side workflow/task state (status `COMPLETED`/`FAILED`/`TERMINATED`, task types like `SUB_WORKFLOW`/`FORK_JOIN`, terminal-fail behavior).

Every suite is written **counterfactually** — each assertion (or a companion contrast test) is designed to fail if the feature under test is broken or silently dropped.

There is no Java equivalent of the `e2e-orchestrator.sh` / TOML runs / LLM judge / HTML report pipeline. Java relies on Gradle's JUnit runner and Gradle's own test reports.

---

## 2. E2E test suite (`sdk/java/e2e/`)

### Layout & framework

- **Framework:** JUnit 5 (`org.junit.jupiter:junit-jupiter`, v5.11.0 — see `sdk/java/build.gradle`).
- **No separate Gradle module.** There is **no** `sdk/java/e2e/build.gradle`. The `e2e/` directory is wired into the SDK's `test` source set:
  ```gradle
  sourceSets { test { java { srcDirs += file('e2e') } } }
  ```
  The e2e classes live in the **default (unnamed) package**.
- **Gating by tag:** every suite class carries `@Tag("e2e")` (25 of the 26 `.java` files; `BaseTest` is the abstract base and is untagged). The default `test` task excludes tag `e2e` unless `-Pe2e` is passed:
  ```gradle
  test { useJUnitPlatform { if (!project.hasProperty('e2e')) excludeTags 'e2e' } }
  ```
  So `./gradlew test` = unit only (fast, no server); `./gradlew test -Pe2e` = unit + e2e.
- **Parallelism:** under `-Pe2e`, `maxParallelForks = 3` (e2e is I/O-bound — LLM/docker — and suites use unique agent/task names, so they fork safely).

### `BaseTest.java` (shared harness)

Abstract base for all suites. Provides:
- **Server health gate (`@BeforeAll`):** GETs `BASE_URL/health`, parses `healthy`, and `assumeTrue(...)`. If the server is down/unhealthy, **all tests in the class are skipped** (not failed). Caveat: a fully-skipped run looks green but proves nothing — always confirm tests actually ran.
- **Config from env:** `AGENTSPAN_SERVER_URL` (default `http://localhost:6767/api`), `AGENTSPAN_LLM_MODEL` (default `openai/gpt-4o-mini`). `BASE_URL` is `SERVER_URL` with `/api` stripped.
- **Workflow fetch:** `getWorkflow(executionId)` → `GET BASE_URL/api/workflow/<id>` for server-side task/status assertions.
- **Plan navigation:** `getAgentDef(CompileResponse)` walks `workflowDef → metadata → agentDef`; `allTasksFlat(workflowDef)` recursively flattens nested tasks (DO_WHILE `loopOver`, SWITCH `decisionCases`/`defaultCase`, FORK_JOIN `forkTasks`).

### What's covered

26 `.java` files in `sdk/java/e2e/` (25 suites + `BaseTest`), **~162 `@Test` methods total** (raw `grep -c "@Test"` across the directory — *approximate*). Note: the class-javadoc "Suite N" labels do not always match the filename numbering (they're carried over from the Python suite mapping); the table below uses the filenames.

| File | Mode | Covers |
|------|------|--------|
| `Suite1BasicValidation` | plan | Basic `plan()` structural assertions on the compiled workflow JSON; counterfactual. |
| `Suite2ToolCalling` | runtime side-effect | Tools actually invoked during execution (asserts via `AtomicBoolean` in tool body, not LLM text / task names). |
| `Suite2ToolCallingCredentials` | runtime status | Runtime credential lifecycle: no-cred → terminal-fail; set/update via API seen at runtime via `ctx.getCredential()`; delete → terminal-fail again. Mirrors the Python/.NET/TS canonical contract. Also verifies env vars are not used as a fallback. |
| `Suite3CliTools` | plan + runtime | `CliConfig` serialization + injected `{name}_run_command` worker; local command execution and whitelist enforcement (executed by the SDK's `CliCommandExecutor`, not the server). |
| `Suite4McpTools` | plan | Server-side MCP tool (`toolType="mcp"`) serialization. |
| `Suite5HttpTools` | plan | Server-side HTTP tool (`toolType="http"`) serialization. |
| `Suite6PdfTools` | plan | Server-side PDF tool (`toolType="generate_pdf"`) serialization. |
| `Suite7MediaTools` | plan | Server-side media tools (image/audio/video/pdf) — `llmProvider`/`model`/`taskType` serialization. |
| `Suite8Guardrails` | runtime status | Guardrails fire at runtime (custom function guardrail always returns `passed=false`) → agent FAILED/TERMINATED. |
| `Suite8bGuardrailsExtended` | plan + runtime | Agent/tool-level guardrail serialization; tool body not blocked by agent OUTPUT guardrail; INPUT max-retries escalation. |
| `Suite9Handoffs` | plan + runtime | SEQUENTIAL / PARALLEL / HANDOFF / PIPE (`.then()`) — correct workflow task types (SUB_WORKFLOW, FORK_JOIN) and completion. |
| `Suite10CodeExecution` | plan + runtime | `localCodeExecution` serialization, injected `execute_code` tool, code actually runs, timeout enforced. |
| `Suite11LangChain4j` | plan + runtime | `LangChain4jAgent` bridge — detection/tagging, tool extraction (JSON Schema), compile, runtime. |
| `Suite11bOpenAIAgent` | plan + runtime | `OpenAIAgent` bridge — same shape as LangChain4j; server routes `framework="openai"` via `OpenAINormalizer`. |
| `Suite12HandoffApprove` | runtime status | HANDOFF + HITL: approval-required tool on a sub-agent → HUMAN task in the sub-execution; targeted `AgentStream.approve(event)`. |
| `Suite12TerminationGates` | runtime status | Termination conditions actually stop execution before `max_turns`. |
| `Suite13Callbacks` | plan + runtime | `CallbackHandler` positions serialize into `agentDef.callbacks`; callbacks don't break execution; multiple handlers. |
| `Suite14StatefulDomain` | plan | `Agent.stateful(...)` propagation into agentDef / tools / swarm sub-agents. |
| `Suite15Skills` | plan | `Skill.skill(path, model)` loads a `SKILL.md` directory as an agent (`framework="skill"`). |
| `Suite16Synthesize` | plan | `synthesize` flag structural effect. |
| `Suite17ConfigSerialization` | plan | Broad serialization round-trip: stateful, baseUrl, TextGate, callbacks, termination, Regex/LLM guardrails, OnCondition handoff, media/wait/human tools, `deploy()`, and parity fields (`reasoningEffort`, `contextWindowBudget`, `maskedFields`, `memory`). Largest suite (~20 tests). |
| `Suite18ToolTypes` | runtime side-effect | Tool-arg coercion pipeline (server task → SDK coerce → method invoke) for `java.time` types; captures the actual received argument via `AtomicReference`. |
| `Suite19ManualStrategy` | runtime status | MANUAL strategy end-to-end: pauses at `pick_agent` HUMAN task, responds with the second agent, asserts the selected sub-workflow ran (catches a broken name→index mapping). |
| `PlanExecuteTest` | runtime | PLAN_EXECUTE strategy end-to-end; assertions are algorithmic (file existence, word counts). |
| `SuiteHttpApi404` | runtime | Live 404 round-trip: `AgentClient` maps a server 404 to `AgentNotFoundException` (not the generic `AgentAPIException`). |

### Server launch & known gotchas

The suites do **not** start the server themselves — they expect one running at `AGENTSPAN_SERVER_URL` and skip if it's not. Launch it yourself (SQLite-backed, no Postgres needed; reads `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` from env):

```bash
cd server
java -jar conductor-agentspan-server/build/libs/agentspan-runtime.jar --server.port=6767
# healthy in ~3-10s; rm agent-runtime.db* for a clean DB
```

> **Known gotchas (verified, local runs):**
> - **Stale-jar `NoClassDefFoundError`:** a prebuilt `agentspan-runtime.jar` can be internally inconsistent — server classes in `BOOT-INF/classes` compiled against a newer API than the bundled `BOOT-INF/lib/conductor-agentspan-*.jar`. Symptom: `/agent/start` (runtime) works but `/agent/compile` (plan tests) and human-task paths 500 with errors like `CompileResponse$CompileResponseBuilder` / `HumanTaskBuilder`. Fix: rebuild — `cd server && ./gradlew :conductor-agentspan-server:bootJar` — then restart.
> - **Default-package discovery:** plain `--tests 'Suite*'` does **not** pick up the default-package classes. Use exact names: `--tests Suite9Handoffs` (or `Suite9Handoffs.<method>`).
> - **Long-run false timeouts:** a single-JVM full run of all suites degrades — worker polling pressure (per-`AgentRuntime` worker threads, 100ms interval) saturates the client pool over hours, so `waitForResult` can miss completions and report `Agent timed out after 600000ms` even though the workflow COMPLETED server-side. Prefer fresh-server batches over one giant run; re-running failed tests on a fresh server passes them.
> - **One Gradle daemon at a time:** concurrent `./gradlew` launches caused daemon contention serving stale results; `./gradlew --stop` to reset.

---

## 3. How to run locally

From `sdk/java/`:

```bash
# Unit tests only (no server, e2e excluded by default):
./gradlew test

# Unit + e2e (requires a live server at AGENTSPAN_SERVER_URL):
./gradlew test -Pe2e

# A single suite (exact class name — default-package, so no wildcard match):
./gradlew test -Pe2e --tests Suite9Handoffs

# A single method:
./gradlew test -Pe2e --tests Suite9Handoffs.<methodName>

# Override server / model:
./gradlew test -Pe2e \
  -DAGENTSPAN_SERVER_URL=http://localhost:6767/api \
  -DAGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
```

Notes:
- Config is read from **env vars** by `BaseTest` (`AGENTSPAN_SERVER_URL`, `AGENTSPAN_LLM_MODEL`); the `-D` system properties above match how CI passes them in the dispatch workflow (see §4) — set them as env vars if `-D` is not picked up in your shell.
- Reports: Gradle writes HTML/XML to `sdk/java/build/reports/tests/test/`.
- Coverage: `./gradlew jacocoTestReport` aggregates whatever ran in `test` (unit-only by default, or unit+e2e under `-Pe2e`). `-PignoreTestFailures` lets a flaky e2e not abort the JaCoCo report.

---

## 4. CI integration

Two workflows run the Java e2e suites; both build/obtain the server JAR, start it on **:6767**, then run `./gradlew test -Pe2e`.

### `ci.yml` — `java-e2e` job (primary, runs in the main pipeline)

`needs: [build-server, java-sdk-tests]`, `timeout-minutes: 45`. Sequence:
1. **Server JAR** is built once by the shared `build-server` job (`./gradlew bootJar -PbuildUI=true -x test` in `server/`) and uploaded as the `server-jar` artifact. `java-e2e` downloads it to `server/conductor-agentspan-server/build/libs/`.
2. **mcp-testkit**: `pip install mcp-testkit`, then `mcp-testkit --transport http --port 3001 &` (test infra for the tool suites — not an SDK dependency).
3. **Start server**: `java -jar .../agentspan-runtime.jar --server.port=6767 &`, then poll `http://localhost:6767/health` (up to 30×2s).
4. **Run**: `./gradlew test -Pe2e` in `sdk/java`.
5. **Artifacts**: `sdk/java/build/reports/tests/test/` uploaded as `java-e2e-results` (always, 14-day retention).

Env: `AGENTSPAN_SERVER_URL=http://localhost:6767/api`, `AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini`, plus `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` from secrets.

The separate **`java-sdk-tests`** job (`./gradlew test :spring:test`) runs the SDK + Spring auto-config **unit** tests only — fast, no server (e2e excluded by default).

### `ci-java-sdk-e2e.yml` — standalone, `workflow_dispatch` only

Manual trigger with optional `model` (default `anthropic/claude-sonnet-4-6`) and `suite` filter inputs. It builds the server JAR inline (`./gradlew bootJar -x test -q` in `server/`) rather than downloading the shared artifact, starts it on :6767 with the same health poll, and runs:
```bash
./gradlew test -Pe2e \
  -DAGENTSPAN_SERVER_URL=$AGENTSPAN_SERVER_URL \
  -DAGENTSPAN_LLM_MODEL=$AGENTSPAN_LLM_MODEL \
  [--tests '*.<suite>*']     # when the suite input is set
```
Note: this dispatch workflow does not start mcp-testkit, so tool suites that need it will skip/fail there — prefer the `ci.yml` `java-e2e` job for a full run. *(Flagged: the `--tests '*.<suite>*'` wildcard pattern here may not match default-package classes the way exact `--tests Suite9Handoffs` does — see the discovery gotcha in §2.)*
