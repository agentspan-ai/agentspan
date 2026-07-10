# Secret delivery toggle: native (standalone) vs host-delivered (embedded)

**Date:** 2026-07-09 · **Status:** In progress · **Branch:** `feature/embedded-secret-toggle`

## Summary

AgentSpan keeps its full native credential mechanism. A single feature flag,
`agentspan.embedded`, toggles it on/off:

| Deployment | `agentspan.embedded` | Secret delivery |
|---|---|---|
| **Standalone** agentspan server | `false` (default) | **Native** — encrypted store, execution-token minting, `POST /api/workers/secrets` pull, SDK fetchers. Unchanged from `main`. |
| **Embedded** in orkes-conductor / conductor-oss | `true` | **Native dormant** (all beans gated off); the **host** delivers secrets. |

## Target design (what we want)

When embedded, secrets are delivered by two distinct mechanisms — deliberately split by task type:

- **Worker tools (SIMPLE tasks) → `TaskDef.runtimeMetadata`.** The agent's worker-tool `TaskDef`
  declares the secret/env names it needs in `runtimeMetadata` (conductor-oss PR #1255). At poll
  time the host resolves each name from its `SecretsDAO`/env and injects the resolved
  `name → value` map onto the **wire-only `Task.runtimeMetadata`** field of the polled task. The
  SDK worker reads `task.runtimeMetadata`. This is the correct home for worker secrets: it is
  never persisted into task input, and it is declarative on the TaskDef.
- **System tasks (LLM `apiKey`, HTTP/MCP/planner headers) → `${workflow.secrets.NAME}`.** These run
  in-process on the host, so the compiler stamps `${workflow.secrets.NAME}` references into the task
  input and the host substitutes them in memory just before execution. These tasks are not polled by
  an external SDK worker, so there is no `Task.runtimeMetadata` to read — `${workflow.secrets.NAME}`
  is the right mechanism for them.

Nothing is deleted; the native code stays intact and active for standalone.

## Required change in each Conductor client SDK  ⬅️ blocking for the target

`Task.runtimeMetadata` is a **new top-level field** on the polled task. Today's client libraries
bundle their own `Task` model with **no such field and no catch-all deserializer**
(`@JsonAnySetter` / additionalProperties), so the value the server injects is **silently dropped on
the wire**. To adopt the target worker path, the `runtimeMetadata` field must be added to the `Task`
model in **each** conductor client library an agentspan SDK depends on, then that client must be
released and the agentspan SDK bumped to it.

The field is always the same shape: JSON key `runtimeMetadata`, a string→string map, output-empty
omitted, **not** persisted server-side (wire-only on the poll response).

| AgentSpan SDK | Client dependency | Client repo | Exact change to the `Task` model |
|---|---|---|---|
| Java | `org.conductoross:conductor-client:5.0.1` | `conductor-oss/java-sdk` | Add `private Map<String,String> runtimeMetadata = new HashMap<>();` + `getRuntimeMetadata()`/`setRuntimeMetadata()` to `com.netflix.conductor.common.metadata.tasks.Task`. Jackson maps the `runtimeMetadata` key automatically (add `@JsonInclude(NON_EMPTY)` to match server). |
| Python | `conductor-python>=1.3.11` | `conductor-oss/python-sdk` | In the generated `Task` model (`conductor/client/http/models/task.py`): add `runtime_metadata` to `swagger_types` (`'dict(str, str)'`), to `attribute_map` (`'runtime_metadata': 'runtimeMetadata'`), and a `@property` + setter. Then `task.runtime_metadata` is populated. |
| C# | `conductor-csharp:1.1.4` | `conductor-oss/csharp-sdk` | Add `public Dictionary<string,string> RuntimeMetadata { get; set; }` to the `Task` model with `[DataMember(Name="runtimeMetadata", EmitDefaultValue=false)]` (and matching `Newtonsoft`/STJ attribute) so the `runtimeMetadata` JSON key binds. |
| TypeScript | `@io-orkes/conductor-javascript:^3.0.3` | Orkes TS SDK (`orkes-io/orkes-conductor-client-js`) | Add `runtimeMetadata?: Record<string,string>` to the `Task` type. JS keeps unknown JSON keys, so the value already survives at runtime — this is a type-definition change for type-safety and for the read-path to compile. |

(Go — `conductor-oss/go-sdk` — would need the same field on its `Task` struct, but AgentSpan ships
no Go SDK, so it is out of scope here.)

Once these land, the agentspan side switches to the target (see "Migration to the target" below).

## Interim implementation (what is shipped on this branch)

Because the client libraries above do **not yet** expose `runtimeMetadata`, this branch ships an
**interim, client-compatible** worker path that requires **no client rebuilds**: the compiler stamps
`inputParameters.__resolved_credentials__ = { NAME: "${workflow.secrets.NAME}" }` on SIMPLE
worker-tool tasks, and the host resolves those references at poll time via PR #1255's
`ParametersUtils.substituteSecrets(task.getInputData())` (walks nested maps, resolves from
`SecretsDAO`). `__resolved_credentials__` rides in the task **input `Map`**, which every client
already preserves, so the SDK worker can read it today. Same security property as the target —
persisted input keeps the reference; plaintext appears only in the poll response.

**System-task delivery is identical to the target already** (`${workflow.secrets.NAME}`), so only the
worker path differs between interim and target.

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

**Part B — system tasks (target, ✅ done).**
`AgentChatCompleteTaskMapper.injectCredentialReferences` stamps
`apiKey = ${workflow.secrets.<PROVIDER_KEY>}` (via `LlmProviderEnv`) when embedded;
`AgentspanAIModelProvider` reads the host-resolved `apiKey` back from task input. HTTP/MCP/planner
headers already branch on `EmbeddedMode.isEmbedded()` to emit `${workflow.secrets.NAME}`.

**Part B — worker tools (interim `__resolved_credentials__`, ✅ done + tested).**
`ToolCompiler.buildWorkerCredConfig` + `JavaScriptBuilder` enrich-script injection +
`AgentCompiler.collectToolCredentials` stamp the `__resolved_credentials__` map onto SIMPLE tasks
(baked as a literal so the `${workflow.secrets}` references resolve at each SIMPLE task's own poll,
not prematurely in the INLINE enrich task). Verified by `ToolCompilerWorkerCredTest` (GraalJS).

## SDK read-path

Each SDK worker **auto-detects**: prefer the host-delivered map, else fall back to the native
token-pull (standalone). The resolved `{name: value}` map feeds the existing injection/accessor
machinery unchanged, and the key is stripped before the handler runs. The native fetcher code stays.

- **Interim (shipped):** read `inputData.__resolved_credentials__`. Done + tested in all four SDKs:
  TS (`worker.ts`/`credentials.ts`), Java (`WorkerManager.readResolvedCredentials`), Python
  (`_dispatch.py`), C# (`WorkerManager.ReadResolvedCredentials`).
- **Target (after the client SDKs ship `runtimeMetadata`):** read `task.runtimeMetadata`
  (`task.runtime_metadata` in Python, `RuntimeMetadata` in C#). Same fallback + injection.

## Migration to the target (once the client SDKs expose `runtimeMetadata`)

1. Land the `Task.runtimeMetadata` field in each client library (table above) and release; bump the
   client version in each agentspan SDK (`sdk/java/build.gradle`, `sdk/python/pyproject.toml`,
   `sdk/csharp/.../*.csproj`, `sdk/typescript/package.json`).
2. **Server:** declare `TaskDef.runtimeMetadata = [names]` on each worker tool's registered `TaskDef`
   (in `AgentService.registerTaskDef`, gated on `EmbeddedMode.isEmbedded()`) instead of stamping
   `__resolved_credentials__`; drop the enrich-script `workerCredCfg` injection. System-task
   `${workflow.secrets}` stamping is unchanged.
3. **SDKs:** switch each worker read-path from `inputData.__resolved_credentials__` to
   `task.runtimeMetadata`; keep the native-fetch fallback.
4. Remove the interim `__resolved_credentials__` stamping/read once all SDKs are on the new clients.

## Dependency

AgentSpan references **no** PR #1255 API — the interim path only emits `${workflow.secrets.NAME}`
strings — so it compiles and tests against the **published** conductor (`conductorVersion =
3.32.0-rc.3`). The `${workflow.secrets.NAME}` references (and, in the target, the
`TaskDef.runtimeMetadata` resolution) are performed **at runtime by the embedded host** conductor's
`ParametersUtils.substituteSecrets` / `RuntimeMetadataResolver` / `SecretsDAO` (conductor-oss
PR #1255). The host must run a conductor build that includes PR #1255; agentspan does not build
against it. (An earlier iteration pinned a local `3.32.0-rc.3-runtimemeta-LOCAL` build — reverted,
because that build's new conductor-side `SecretResource` shadowed agentspan's `SecretController`
`GET /api/secrets` in standalone tests.)

## Tests

- `NativeSecretGatingTest` ✅ — native beans present standalone, absent embedded
  (`ApplicationContextRunner`); fail-first validated.
- `ToolCompilerWorkerCredTest` ✅ — GraalJS-executes the enrich script; SIMPLE task carries
  `__resolved_credentials__` when embedded, nothing standalone; fail-first validated.
- `ReadResolvedCredentialsTest` (Java) ✅, `test_resolved_credentials.py` (Python) ✅, TS
  `credentials.test.ts` ✅ — host-delivered read-path, all fail-first validated.
- Full CI green: server-tests, build-server, all four SDK unit + e2e suites.

## Status snapshot

| Item | State |
|---|---|
| Part A — native mechanism gated on `agentspan.embedded` | ✅ done + tested |
| System-task `${workflow.secrets}` (target = shipped) | ✅ done |
| Worker-tool delivery — **interim** `__resolved_credentials__` | ✅ done + tested (shipped) |
| Worker-tool delivery — **target** `TaskDef.runtimeMetadata` | ⏳ blocked on client-SDK `runtimeMetadata` field (table above) |
| SDK read-path — interim (`__resolved_credentials__`), all 4 SDKs | ✅ done (C# not run locally — CI green) |
| SDK read-path — target (`task.runtimeMetadata`), all 4 SDKs | ⏳ after client SDKs ship the field |
