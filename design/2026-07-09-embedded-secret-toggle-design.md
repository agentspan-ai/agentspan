# Secret delivery toggle: native (standalone) vs host-delivered (embedded)

**Date:** 2026-07-09 · **Status:** In progress · **Branch:** `feature/embedded-secret-toggle`

## Summary

AgentSpan keeps its full native credential mechanism and toggles it with one flag, `agentspan.embedded`:

| Deployment | `agentspan.embedded` | Secrets |
|---|---|---|
| **Standalone** agentspan server | `false` (default) | **Native**: encrypted store, execution-token minting, `/api/workers/secrets` pull, SDK fetchers. Unchanged from `main`. |
| **Embedded** in orkes-conductor / conductor-oss | `true` | **Native dormant** (beans gated off); the **host** resolves secrets. |

Nothing is deleted — the native code stays intact for standalone.

## How secrets are delivered when embedded (split by task type)

- **Worker tools (SIMPLE, polled by the SDK)** → the worker's `TaskDef.runtimeMetadata` declares the
  secret names; the host resolves them at poll and injects the values onto the **wire-only
  `Task.runtimeMetadata`**. This is the **target**. Until the client SDKs expose that field (see
  table), we ship an **interim**: the compiler stamps
  `inputParameters.__resolved_credentials__ = {NAME: "${workflow.secrets.NAME}"}` and the host
  resolves it — same delivery, but it rides in the task-input `Map` that today's clients already keep.
- **System tasks (LLM `apiKey`, HTTP/MCP/planner headers — in-process on the host)** → the compiler
  stamps `${workflow.secrets.NAME}` into task input; the host substitutes in memory before the call.
  Not polled by a worker, so there's no `Task.runtimeMetadata` to read. Identical for target and interim.

## Interim worker path (enrichment) — how it actually works

Worker tools aren't static: the LLM picks them, an **INLINE "enrich" task** (GraalJS) builds the
SIMPLE tasks at runtime, and a `FORK_JOIN_DYNAMIC` schedules them. The per-tool cred map is baked
into the enrich script at compile time.

```mermaid
sequenceDiagram
    autonumber
    participant C as Compiler
    participant WF as WorkflowDef
    participant LLM as LLM task
    participant EN as Enrich task (INLINE / GraalJS)
    participant H as Host (Orkes secretsDAO)
    participant FK as FORK_JOIN_DYNAMIC
    participant W as SDK worker (SIMPLE task)
    participant T as Tool fn

    Note over C,WF: compile / register time (embedded only)
    C->>C: collectToolCredentials(agent) - tool creds, agent-level fallback
    C->>C: buildWorkerCredConfig - map each tool to its workflow.secrets refs
    C->>WF: bake the cred map into the enrich INLINE script
    Note over LLM,T: execution time
    LLM->>EN: toolCalls (which tools to run)
    H->>EN: substituteSecrets resolves the secret refs to plaintext
    Note right of EN: caveat - resolves here, not at the SIMPLE task poll
    EN->>EN: set inputParameters.__resolved_credentials__ on each SIMPLE task
    EN->>FK: dynamicTasks
    FK->>W: schedule and poll the SIMPLE task
    W->>W: read __resolved_credentials__, set CredentialContext, strip key
    W->>T: run tool, then get_secret(NAME) returns the value
    T-->>W: result
```

**Caveat:** because the reference is baked into the INLINE script, the host resolves
`${workflow.secrets.NAME}` **at the enrich step**, not at the SIMPLE task's poll. So plaintext lands
in the forked task's **persisted** input, and a secret with JS-special chars (`"`, `\`, newline) can
break the script. The target fixes both.

## Target vs interim — same runtime cost, better safety

`get_secret(NAME)` (and `getCredential` / `ToolContext.getCredential` / `Secrets.Get`) is an
**in-memory lookup**: the worker stashes the resolved `{NAME: value}` map in a per-invocation context
and the accessor reads it. When embedded, the value is delivered **inline with the task** (poll
response) in both paths — **no extra calls** (only the standalone native path calls
`/api/workers/secrets`). So the choice is about safety, not performance — the target wins on:

1. **Wire-only, never persisted** — `Task.runtimeMetadata` is on the poll response only; the interim
   bakes plaintext into the forked task's persisted input (visible in execution history).
2. **No JS-injection** — declared names on the TaskDef vs a `${...}` reference baked into GraalJS
   (special chars break it).
3. **Resolved at the SIMPLE task's own poll**, scoped to that task — not early, in a shared enrich task.
4. **First-class & declarative** — the conductor-native field vs a magic `__resolved_credentials__` key.

Cost: the target needs the client libraries to expose `Task.runtimeMetadata` first — which is why the
interim ships now.

## Required change in each Conductor client SDK (blocks the target)

`Task.runtimeMetadata` is a new top-level field; today's clients drop it on the wire (no field, no
catch-all deserializer). Add it to each client's `Task` model (JSON key `runtimeMetadata`,
string→string, output-empty omitted), release, and bump the SDK's client dependency.

| AgentSpan SDK | Client dependency | Client repo | Change to the `Task` model |
|---|---|---|---|
| Java | `org.conductoross:conductor-client:5.0.1` | `conductor-oss/java-sdk` | Add `Map<String,String> runtimeMetadata` + getter/setter to `com.netflix.conductor.common.metadata.tasks.Task` (Jackson auto-maps; `@JsonInclude(NON_EMPTY)`). |
| Python | `conductor-python>=1.3.11` | `conductor-oss/python-sdk` | In `.../models/task.py`: add `runtime_metadata` to `swagger_types`/`attribute_map` (`'runtimeMetadata'`) + property. |
| C# | `conductor-csharp:1.1.4` | `conductor-oss/csharp-sdk` | Add `Dictionary<string,string> RuntimeMetadata` with `[DataMember(Name="runtimeMetadata", EmitDefaultValue=false)]`. |
| TypeScript | `@io-orkes/conductor-javascript:^3.0.3` | Orkes TS SDK | Add `runtimeMetadata?: Record<string,string>` to the `Task` type (JS keeps unknown keys; this is a type-def change so the read-path compiles). |

(Go is out of scope — AgentSpan ships no Go SDK.)

## Implementation (done + tested; CI green)

- **Gating:** `@ConditionalOnProperty(agentspan.embedded=false, matchIfMissing=true)` on every native
  secret bean — `WorkerController`, `CredentialResolutionService`, `ExecutionTokenService`,
  `CredentialAwareMcpService`, `CredentialMaskingResponseAdvice`, `EncryptedDbCredentialStoreProvider`,
  `MasterKeyConfig`, `CredentialEnvSeeder`, `CredentialSchemaMigrator`, `CredentialDataSourceConfig`,
  `NoOpSecretOutputMasker`. Active consumers made tolerant: `AgentspanAIModelProvider` (`ObjectProvider`
  + guards); `AgentService` / `AgentEventListener` (`@Autowired(required=false)` + null guards, so token
  minting is skipped).
- **System tasks:** `AgentChatCompleteTaskMapper.injectCredentialReferences` + `LlmProviderEnv` stamp
  `apiKey=${workflow.secrets.<KEY>}`; `AgentspanAIModelProvider` reads it back. HTTP/MCP/planner headers
  already emit `${workflow.secrets.NAME}`.
- **Worker tools (interim):** `ToolCompiler.buildWorkerCredConfig` + `JavaScriptBuilder` enrich
  injection + `AgentCompiler.collectToolCredentials`.
- **SDK read-path (all 4):** prefer the host map, else native token-pull; feed the existing accessor;
  strip the key. Interim reads `inputData.__resolved_credentials__`; target reads `task.runtimeMetadata`.
- **Tests (all fail-first validated):** `NativeSecretGatingTest`, `ToolCompilerWorkerCredTest`
  (GraalJS-runs the enrich script), `ReadResolvedCredentialsTest` (Java), `test_resolved_credentials.py`
  (Python), TS `credentials.test.ts`.

## Migration to the target (when clients expose `runtimeMetadata`)

1. Land the field in each client (table), release, bump the SDK client versions.
2. **Server:** set `TaskDef.runtimeMetadata=[names]` in `AgentService.registerTaskDef` (embedded-gated);
   drop the enrich `workerCredCfg` injection. System-task stamping unchanged.
3. **SDKs:** read `task.runtimeMetadata` instead of `inputData.__resolved_credentials__`; keep the
   native fallback.
4. Remove the interim once all SDKs are on the new clients.

## Dependency

AgentSpan uses no PR #1255 API, so it builds/tests against the published `conductor 3.32.0-rc.3`.
`${workflow.secrets.NAME}` (and, in the target, `TaskDef.runtimeMetadata`) are resolved **at runtime
by the embedded host** (`substituteSecrets` / `RuntimeMetadataResolver` / `SecretsDAO`, PR #1255) — the
host must include PR #1255; agentspan does not build against it. (An earlier local
`…-runtimemeta-LOCAL` pin was reverted: its conductor-side `SecretResource` shadowed agentspan's
`SecretController` `GET /api/secrets` in standalone tests.)

## Status

| Item | State |
|---|---|
| Native mechanism gated on `agentspan.embedded` | ✅ done + tested |
| System-task `${workflow.secrets}` delivery | ✅ done |
| Worker tools — interim `__resolved_credentials__` (server + 4 SDKs) | ✅ done + tested (CI green) |
| Worker tools — target `TaskDef.runtimeMetadata` | ⏳ blocked on client-SDK field (table) |
