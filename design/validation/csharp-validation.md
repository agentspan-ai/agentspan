# C# SDK — Validation & E2E

**Status:** Created 2026-06-26

**Scope:** How the C# SDK is validated end-to-end against a real Agentspan server. Unlike the Python and TypeScript SDKs — which add a separate *examples-quality* validation framework (model matrix runs + LLM-as-judge scoring; see [`python-validation.md`](python-validation.md) and [`typescript-validation.md`](typescript-validation.md)) — C# has **no examples-quality / LLM-judge framework**. C# validation is a single **deterministic** xUnit e2e suite (`AgentspanE2eTests`) plus one standalone guardrail-matrix example program (`90_GuardrailE2eTests`). Per `CLAUDE.md`, the e2e suite never uses an LLM to *judge* output; assertions are JSON-path / object-graph / status checks (the only LLM calls are the agent runs themselves). Related: [`README.md`](README.md) (methodology), [`../sdk-design/languages/csharp-implementation.md`](../sdk-design/languages/csharp-implementation.md) (implementation), [`../sdk-design.md`](../sdk-design.md) (cross-SDK design).

---

## 1. Overview

C# validation has two layers:

1. **`AgentspanE2eTests`** — the xUnit e2e project at `sdk/csharp/tests/AgentspanE2eTests/`. This is the authoritative regression suite. It mirrors the Python e2e helpers and suite numbering (the source comments cross-reference Python's `_agent_def()`, `_tool_names()`, `_get_workflow()`, etc.).
2. **`90_GuardrailE2eTests`** — a standalone `Exe` example at `sdk/csharp/examples/90_GuardrailE2eTests/` that exercises the full 27-cell guardrail matrix (Position × Type × OnFail) against a live server, printing a PASS/FAIL table and exiting non-zero on any failure. It is run as a program, **not** via `dotnet test`.

**No LLM judge.** There is no `validation/` directory, no `runs.toml`, no model-matrix orchestrator, and no scoring rubric on the C# side. Output quality is never machine-graded. This is intentional and consistent with `CLAUDE.md` rule 1 (no LLM for validation unless judging quality) — every C# assertion is deterministic.

**Assembly name note.** The test assembly is intentionally named `AgentspanE2eTests` (not renamed to match the `Conductor.AI` namespace move). The production library `Conductor.AI` grants `[assembly: InternalsVisibleTo("AgentspanE2eTests")]` (see `sdk/csharp/src/Conductor.AI/Conductor.AI.csproj`), so renaming the assembly would break tests that inspect `internal` SDK members (tool `ToolType`/`Config`, etc.). The CI filter `FullyQualifiedName!~AgentspanE2eTests` also depends on this exact name. Namespace inside the project is `Conductor.AI.E2eTests`.

---

## 2. E2E test suite

### Layout & framework

- Project: `sdk/csharp/tests/AgentspanE2eTests/AgentspanE2eTests.csproj`
  - `net10.0`, `IsTestProject=true`, `IsPackable=false`
  - Framework: **xUnit** (`xunit` 2.9.3, `xunit.runner.visualstudio`, `Microsoft.NET.Test.Sdk` 17.12.0) plus **`Xunit.SkippableFact`** 1.4.13 for server-gated skipping
  - References the SDK `../../src/Conductor.AI/Conductor.AI.csproj` and compiles in the shared `../../examples/Shared/Settings.cs`
- ~26 `.cs` files; **~175** `[Fact]` / `[SkippableFact]` methods total *(approximate — grep count of `[Fact]`/`[SkippableFact]`/`[Theory]` attributes; no `[Theory]` cases present)*.

### Server gating

- `E2eFixture.cs` (collection fixture `[CollectionDefinition("E2e")]`) does a one-time `GET {server}/health` in `InitializeAsync`. Server base is derived from `AGENTSPAN_SERVER_URL` (default `http://localhost:6767/api`, with `/api` stripped for the health probe).
- Tests call `RequireServer()` → `Skip.IfNot(ServerAvailable, …)`. **When the server is unreachable, server-dependent tests skip rather than fail**, so CI stays green without a running server.
- `E2eFixture.FetchWorkflowAsync(executionId)` fetches `GET {server}/api/workflow/{id}?includeTasks=true` for runtime-state assertions (mirrors Python's `_get_workflow`).
- `E2eHelpers.cs` provides deterministic plan-navigation helpers: `GetAgentDef`, `AllTasksFlat` (recurses loop/decision/fork tasks), `ToolNames`, `GetTool`, `GetToolType`, `GetToolCredentials`, `GuardrailNames`, `GetGuardrail`, `SubAgentNames`.

### Test-tier convention

Suites split tests into two tiers, called out in file-header comments:

- `[Fact]` — pure in-process SDK tests (no server, no LLM). Inspect `ToolDef`/`Agent`/builder properties and serialization. Run in both the unit job and the e2e job.
- `[SkippableFact]` — server tests. Compile via `PlanAsync()` and assert on the compiled plan JSON, or `RunAsync()` and assert on `result.Status` / runtime task graph. Some `RunAsync` tests do invoke an LLM, but assertions are on **status / structure / tool side-effect counters**, never on judged text.

### Coverage (suites)

*Counts below are approximate grep tallies of `[Fact]`/`[SkippableFact]`.*

| File | ~Tests | Covers |
|------|-------:|--------|
| `Suite1_BasicValidation.cs` | 11 | AgentDef JSON exactness: toolType, credentials, guardrailType/position/onFail/maxRetries, strategy, model, instructions, maxTurns; worker/http/credential tool types; multi-guardrail; handoff strategy; all-strategies wire values |
| `Suite2_ToolCalling.cs` | 5 | Single/multi/async tool function-body execution; tool result in execution; runtime credential-lifecycle injection |
| `Suite3_Guardrails.cs` | 4 | Output/regex/tool guardrail function-body execution; passing guardrail → agent succeeds |
| `Suite4_Termination.cs` | 8 | maxMessage / textMention / stopMessage / composed-OR termination in plan; runtime maxTurns / textMention / maxMessage stop-early; invalid-model runtime failure |
| `Suite5_Strategies.cs` | 9 | Handoff/sequential/parallel/swarm/router compile; pipeline operator → sequential; runtime sequential/parallel/handoff execution |
| `Suite6_Callbacks.cs` | 5 | before/after model callbacks fire; both fire; callback around tool calls; callbacks present in plan |
| `Suite7_Credentials.cs` | 6 | ToolDef credential props; external ToolDef compiles; local credential tool → worker type in plan |
| `Suite8_CodingAgents.cs` | 9 | Coding swarm strategy/sub-agent count; GitHub agent tools in plan; CLI-tool-with-credentials; chained pipeline (sequential + termination); local file tools execute |
| `Suite9_McpTools.cs` | 12 | MCP/http tool ToolDef props; mcp/http types in plan; mixed agent (all three tool types); MCP credential tool |
| `Suite10_CodeExecutionAndDeploy.cs` | 12 | Docker/serverless executors compile in plan; serverless POSTs code; discovered agents compile + run-by-name; local Python runtime output; local timeout kills long-running code |
| `Suite11_CliTools.cs` | 10 | CLI ToolDef props; allowed-command execution + description blocking; worker type in plan; CLI-tool-with-credentials |
| `Suite12_HttpTools.cs` | 10 | HTTP ToolDef props; http type in plan; http-tool-with-credentials; agent with only http tools has no worker tools |
| `Suite13_StatefulDomain.cs` | 13 | `Agent.Stateful` serialization; worker tool stateful flag in plan; two stateful agents compile independently; **concurrent runs have disjoint domains**; per-tool stateful propagation + domain isolation |
| `Suite14_PdfTools.cs` | 5 | PDF tool type + default schema (markdown/filename); custom name/description round-trip; PDF generation task completes |
| `Suite15_MediaTools.cs` | 5 | image/audio/video tool types in plan; multiple distinct media types; OpenAI image generation completes |
| `Suite16_PlanExecuteRefs.cs` | 2 | `Ref` pipes whole output across plan-execute steps; two refs resolve independently |
| `Suite16_Skills.cs` | 3 | Skill loads → deterministic plans/workers; skill-as-agent-tool carries worker names for domain routing; standalone skill script runs as worker tool |
| `Suite17_SdkParity.cs` | 8 | Cross-SDK parity: handoff triggers serialize, text gate, dynamic instructions resolve fresh, lifecycle callbacks (agent/tool + composable), `[AgentDef]`+`FromInstance`, worker-tuning env vars |
| `Suite18_AgentClient.cs` | 3 | `AgentClient` (renamed from `AgentHttpClient`): control-plane-only `RunAsync` (start+poll, no local workers); `ScheduleAsync` create/list/purge lifecycle |
| `Suite19_AuthHeader.cs` | 4 | `AgentAuthHandler`: mints JWT from key+secret → sends `X-Authorization` (Orkes contract) + caches; key-only treated as token (no mint); no-creds → no header. In-memory stub handlers, no server |
| `Plans_ContextTests.cs` | 8 | `Context` dataclass + serializer (no LLM) |
| `Plans_OpTests.cs` | 5 | `Op` XOR invariant — exactly one of `Args` / `Generate`, enforced at construction time |
| `ScheduleTests.cs` | 15 | Scheduling SDK: unit tests + integration (`ScheduleIntegrationTests`) — reconcile/upsert/prune/pause/resume/empty-purge/null-preserve/delete-then-get/preview-next (integration skipped unless scheduler reachable) |
| `CredentialInjectionConcurrentTest.cs` | 3 | Secret-injection contract (per `docs/design/secret-injection-contract.md §5`): counterfactual race proof + fix-verification; deterministic via `Barrier`/`ManualResetEventSlim`, no sleeps |

> Note: the `ci.yml` comment says "101 tests across 13 suites" — that figure is **stale**; the suite has grown to ~175 tests across the files above. Flagged for a future doc/comment sync.

### Guardrail matrix example (`90_GuardrailE2eTests`)

- Standalone `Exe` (`Example90GuardrailE2eTests.csproj`, `net10.0`), references `Conductor.AI` and `Shared/Settings.cs`. **Not** a `dotnet test` project — it is `dotnet run`.
- Builds 27 agents = Position (Agent-OUT / Tool-INPUT / Tool-OUTPUT) × Type (Regex / LLM / Custom) × OnFail (RETRY / RAISE / FIX), runs each against a live server, and checks each via an in-program `TestRunner.Check(...)`.
- Assertions are deterministic: `expectStatus` / `expectStatusIn` (e.g. `Status.Failed` for RAISE), `expectContains` / `expectNotContains` substring checks (e.g. output must NOT contain `SECRET42`, must contain `REDACTED` after a FIX). No LLM judging — the LLM is only the agent under test.
- Prints a 27-row PASS/FAIL/SKIP table with execution IDs and `Environment.Exit(failed > 0 ? 1 : 0)`.
- Requires `AGENTSPAN_SERVER_URL`, `AGENTSPAN_LLM_MODEL`, and `OPENAI_API_KEY` (LLM guardrail cells).

---

## 3. How to run locally

Prerequisites: .NET 10 SDK; a running Agentspan server on `:6767`; `OPENAI_API_KEY` for tests that actually run an agent. Without a reachable server, `[SkippableFact]` tests skip and `[Fact]` tests still run.

Start the server (from a built jar):

```bash
java -jar server/conductor-agentspan-server/build/libs/agentspan-runtime.jar --server.port=6767
```

Run the full e2e suite (exact command, from `sdk/csharp/`):

```bash
dotnet test tests/AgentspanE2eTests/AgentspanE2eTests.csproj --configuration Release
```

Filter to one suite (matches the `ci-csharp-sdk-e2e.yml` `suite` input):

```bash
dotnet test tests/AgentspanE2eTests/AgentspanE2eTests.csproj \
  --configuration Release \
  --filter "FullyQualifiedName~Suite1_BasicValidation"
```

Run **only** the in-process (no-server) unit-tier tests — this is what the `csharp-sdk-tests` CI job does (it excludes the whole e2e assembly by name):

```bash
dotnet test Agentspan.sln \
  --configuration Release \
  --filter "FullyQualifiedName!~AgentspanE2eTests"
```

Run the guardrail-matrix example (standalone program, not `dotnet test`), from `sdk/csharp/`:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
export OPENAI_API_KEY=...
dotnet run --project examples/90_GuardrailE2eTests
```

Environment variables (from `examples/Shared/Settings.cs`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server endpoint (health probe strips `/api`) |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o-mini` | Model for agent runs |
| `OPENAI_API_KEY` | — | Required for `RunAsync`/LLM-guardrail tests |

---

## 4. CI integration

Two GitHub Actions paths exercise C# e2e.

### `ci.yml` (gating, on push/PR)

- **`csharp-sdk-tests`** — builds `Agentspan.sln` (Release) and runs unit-tier tests with `--filter "FullyQualifiedName!~AgentspanE2eTests"` (excludes the e2e assembly so no live server is needed). Uploads `.trx` results.
- **`csharp-e2e`** — `needs: [build-server, csharp-sdk-tests]`, 45-min timeout. Sets up Java 21 + .NET 10, downloads the prebuilt `server-jar` artifact, starts it on `:6767` and polls `/health`, then runs:
  ```bash
  dotnet test tests/AgentspanE2eTests/AgentspanE2eTests.csproj \
    --configuration Release \
    --logger "console;verbosity=normal" \
    --logger "trx;LogFileName=csharp-e2e.trx"
  ```
  Env: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AGENTSPAN_SERVER_URL=http://localhost:6767/api`, `AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini`. Mirrors the python/typescript/java e2e jobs (same `build-server` prerequisite, same `:6767` startup). Uploads `.trx` results. *(The header comment "101 tests across 13 suites" is stale; see §2.)*

### `ci-csharp-sdk-e2e.yml` (manual)

- `workflow_dispatch` only, with inputs `model` (default `openai/gpt-4o-mini`) and `suite` (filter, e.g. `Suite1_BasicValidation`).
- Builds the server JAR in-line (`./gradlew bootJar -x test -q` in `server/`), sets up Java 21 + .NET 10, starts `agentspan-runtime.jar --server.port=6767`, polls `/health` (30 × 2s), then runs `dotnet test tests/AgentspanE2eTests/AgentspanE2eTests.csproj --configuration Release` with an optional `--filter FullyQualifiedName~<suite>`.
- Env: `AGENTSPAN_SERVER_URL`, `AGENTSPAN_LLM_MODEL` (from input), `OPENAI_API_KEY`. Stops the server in an `always()` step.

The guardrail-matrix example (`90_GuardrailE2eTests`) is not wired into either CI workflow — it is a manual/local diagnostic that exits non-zero on failure.

---

## Uncertainties / flags

- Test counts are **approximate** grep tallies of `[Fact]`/`[SkippableFact]` attributes; the true count of executed test cases may differ slightly (no parameterized `[Theory]` cases were found).
- `ci.yml`'s "101 tests across 13 suites" comment is out of date relative to the current ~175 tests / ~26 files.
- Confirmed absence of a C# examples-quality / LLM-judge validation framework as of this writing (no `validation/` dir, no `runs.toml` under `sdk/csharp/`).
