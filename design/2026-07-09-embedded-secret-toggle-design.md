# Secret delivery toggle: native (standalone) vs host-delivered (embedded)

**Date:** 2026-07-09 · **Status:** In progress · **Branch:** `feature/embedded-secret-toggle`

## Summary

AgentSpan keeps its full native credential mechanism. A single feature flag,
`agentspan.embedded`, toggles it on/off:

| Deployment | `agentspan.embedded` | Secret delivery |
|---|---|---|
| **Standalone** agentspan server | `false` (default) | **Native** — encrypted store, execution-token minting, `POST /api/workers/secrets` pull, SDK fetchers. Unchanged from `main`. |
| **Embedded** in orkes-conductor / conductor-oss | `true` | **Native dormant** (all beans gated off); the **host** resolves `${workflow.secrets.NAME}`. |

**Everything embedded flows through `${workflow.secrets.NAME}`** — no new wire fields, no
client-library changes. The host resolves those references from its secret store:
- **System tasks** (LLM `apiKey`, HTTP/MCP/planner headers) — `${workflow.secrets.NAME}` in task
  input, resolved in-process before the task runs.
- **Worker tools** (SIMPLE tasks) — `inputParameters.__resolved_credentials__ = { NAME:
  "${workflow.secrets.NAME}" }`, resolved at poll time by conductor-oss PR #1255's
  `ParametersUtils.substituteSecrets(task.getInputData())` (which walks nested maps and resolves
  each reference from the `SecretsDAO`). The SDK worker reads `__resolved_credentials__` from the
  task input and strips it.

Nothing is deleted; the native code stays intact and active for standalone.

## Why `${workflow.secrets}` in input, not `Task.runtimeMetadata`

PR #1255 offers two poll-time delivery paths. We deliberately use only the input-reference one:

- **`Task.runtimeMetadata`** (rejected) is a *new top-level field* on the polled Task. The SDK
  polling clients bundle their own `Task` model — `conductor-client:5.0.1` (Java),
  `conductor-csharp:1.1.4`, `conductor-python:1.3.11` — none of which have that field or an
  `@JsonAnySetter`, so the value is silently dropped on the wire. Using it would force **rebuilding
  and republishing all three client libraries** (separate `conductor-oss/java-sdk`, `csharp-sdk`,
  `python-sdk` repos). Not worth it.
- **`__resolved_credentials__` in `inputData`** (chosen) lives in the task's input `Map`, which
  every client already preserves as-is. Same security property — the persisted input keeps the
  `${workflow.secrets.NAME}` *reference*; plaintext appears only in the poll response. **No client
  rebuilds, no `conductor-client` version bump.**

## Server changes

**Part A — gate the native mechanism. ✅ Done + tested.** Every native secret bean carries
`@ConditionalOnProperty(name = "agentspan.embedded", havingValue = "false", matchIfMissing = true)`
so it is absent when embedded: `WorkerController`, `CredentialResolutionService`,
`ExecutionTokenService`, `CredentialAwareMcpService`, `CredentialMaskingResponseAdvice`,
`EncryptedDbCredentialStoreProvider`, `MasterKeyConfig`, `CredentialEnvSeeder`,
`CredentialSchemaMigrator`, `CredentialDataSourceConfig`, `NoOpSecretOutputMasker` (plus the
already-gated `SecretController`, `CredentialAwareHttpTaskConfig`). Consumers that stay active
tolerate their absence: `AgentspanAIModelProvider` injects the two services via `ObjectProvider`
(null when embedded, guarded at each use); `AgentService` / `AgentEventListener` already use
`@Autowired(required = false)` + null guards (so token minting is simply skipped when embedded).

**Part B — system-task host delivery. ✅ Done.**
`AgentChatCompleteTaskMapper.injectCredentialReferences` stamps `apiKey =
${workflow.secrets.<PROVIDER_KEY>}` (via `LlmProviderEnv`) when embedded; `AgentspanAIModelProvider`
reads the host-resolved `apiKey` back from task input. HTTP/MCP/planner headers already branch on
`EmbeddedMode.isEmbedded()` to emit `${workflow.secrets.NAME}` (unchanged from `main`).

**Part B — worker-tool host delivery. ✅ Done + tested.** Stamps
`inputParameters.__resolved_credentials__ = { NAME: "${workflow.secrets.NAME}" }` on SIMPLE
worker-tool tasks, embedded only (ported from `fa64a9cc`, keeping the native code):
- `ToolCompiler`: `workerCreds` map + `setWorkerCreds`, `NON_WORKER_TOOL_TYPES`/`isWorkerTool`,
  `buildWorkerCredConfig` (builds `{tool -> {NAME: "${workflow.secrets.NAME}"}}`), and thread a
  `workerCredJson` literal into the enrich script.
- `JavaScriptBuilder`: the enrich script injects `t.inputParameters.__resolved_credentials__ =
  workerCredCfg[name]` onto each dynamically-forked SIMPLE task (baked as a literal so the
  `${workflow.secrets}` references are *not* resolved prematurely by the in-process INLINE enrich
  task — they resolve at each SIMPLE task's own poll).
- `AgentCompiler`: `collectToolCredentials` / `collectCredentialUnion` (per-tool names with
  agent-level fallback) + direct `__resolved_credentials__` stamping on the static prefill and
  framework-passthrough SIMPLE tasks; wire `setWorkerCreds(...)`.
- `MultiAgentCompiler`: wire `setWorkerCreds(...)`.
- Test with `ToolCompilerWorkerCredTest` (GraalJS-executes the enrich script and asserts the built
  SIMPLE task carries `__resolved_credentials__` when embedded, nothing when standalone).

## SDK read-path — why every SDK must change

The resolved secrets arrive on `inputData.__resolved_credentials__` (embedded) instead of the
native `/api/workers/secrets` pull (standalone). Each SDK worker must therefore **auto-detect**:
prefer `inputData.__resolved_credentials__` when present; otherwise fall back to the existing
native token-pull fetcher. The resolved `{NAME: value}` map feeds the existing injection/accessor
machinery unchanged, and the key is stripped before the handler runs. The native fetcher code stays.
No client-library change is needed (the map rides in the preserved `inputData`).

- **TypeScript — ✅ Done + tested.** `worker.ts` prefers `inputData.__resolved_credentials__`,
  else native pull; `getCredential` reads the host-delivered map from the credential context;
  `stripInternalKeys` drops the key. Unit tests in `credentials.test.ts` (fail-first validated).
- **Java — ✅ Done + tested.** `internal/WorkerManager.java` `executeHandler`: `readResolvedCredentials(inputData)`
  (non-empty → use it) else `credentialFetcher.fetch(execToken, declared)`; feeds `CredentialContext`.
  `ReadResolvedCredentialsTest` (fail-first validated); root SDK suite green.
- **Python — ✅ Done + tested.** `runtime/_dispatch.py`: pops `task.input_data["__resolved_credentials__"]`
  (non-empty → use it) else the token-pull fetcher; feeds the contextvar / `inject_via_env`.
  `test_resolved_credentials.py` (fail-first validated).
- **C# — ✅ Done (not run locally — no `dotnet` toolchain here).** `WorkerManager.cs`:
  `ReadResolvedCredentials(inputData)` (non-empty → use it) else `ResolveCredentialsAsync(...)`; feeds
  `CredentialScope`; strips the key from handler input. Mirrors the Java/Python logic; needs a
  `dotnet test` run in CI to confirm.

## Dependency

Requires a conductor build with PR #1255 (`ParametersUtils.substituteSecrets` + `SecretsDAO`
resolution of `${workflow.secrets.NAME}` in task input at poll). Currently built from
`conductor-oss` `feat/env-backed-secrets-and-environment` → mavenLocal
`3.32.0-rc.3-runtimemeta-LOCAL` (superset of 3.32.0-rc.3), pinned in `server/build.gradle`. Revert
to a published version once PR #1255 ships. **No SDK client-library changes are required.**

## Tests

- `NativeSecretGatingTest` ✅ — native beans present standalone, absent embedded
  (`ApplicationContextRunner`); fail-first validated.
- TS `credentials.test.ts` ✅ — host-delivered map read by `getCredential` without an endpoint pull;
  undelivered secret with no token → NotFound (off-host trim); fail-first validated.
- Planned: `ToolCompilerWorkerCredTest` (GraalJS enrich-script assertion), and Java/C#/Python SDK
  unit tests for the `__resolved_credentials__` auto-detect.
- Standalone credential e2e suites remain unchanged and green.

## Status snapshot

| Item | State |
|---|---|
| Part A — native mechanism gated on `agentspan.embedded` | ✅ done + tested |
| System-task `${workflow.secrets}` (LLM apiKey, HTTP/MCP/planner headers) | ✅ done |
| Conductor `runtimemeta` build + pin | ✅ done |
| Worker-tool `__resolved_credentials__` server stamping | ✅ done + tested (`ToolCompilerWorkerCredTest`, fail-first) |
| TypeScript SDK read-path | ✅ done + tested |
| Java SDK read-path | ✅ done + tested (`ReadResolvedCredentialsTest`, fail-first) |
| Python SDK read-path | ✅ done + tested (`test_resolved_credentials.py`, fail-first) |
| C# SDK read-path | ✅ done (not run locally — needs `dotnet test` in CI) |
