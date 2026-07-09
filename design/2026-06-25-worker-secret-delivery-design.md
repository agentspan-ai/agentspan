# Credential Delivery via `${workflow.secrets.NAME}`

**Date:** 2026-06-25 · **Status:** Implemented · **Branch:** `feature/fix_webhook_execution_token`

## Summary

AgentSpan adds nothing of its own for secrets. The compiler emits Conductor-native
`${workflow.secrets.NAME}` references into task input and lets **Orkes-Conductor's existing
secret mechanism** resolve them. No agentspan store, secrets API, token, or in-process
resolution.

Because the resolver is Orkes-Conductor's — not ours, and not in OSS Conductor — secrets
work in exactly one deployment:

| Deployment | `agentspan.embedded` | Secrets? |
|---|---|---|
| Embedded in **Orkes-Conductor** | `true` | **Yes** — Orkes resolves the references |
| Embedded in **OSS Conductor** | `true` | No — references stamped, but OSS resolves `${workflow.secrets.X}` to `null` |
| **Standalone** | `false` | No — references not stamped |

The two "No" modes are non-secure by design. There is nothing to operate or secure.

### What OSS Conductor actually does with the reference

OSS Conductor has no secret store. Its `ParametersUtils.replaceVariables` evaluates
`${workflow.secrets.NAME}` as a JSONPath over the workflow context with
`Option.SUPPRESS_EXCEPTIONS`; since the workflow has no `secrets` node, the read returns
`null`. So a worker tool either gets `null` (embedded on OSS) or no credential field at all
(standalone — the reference is never stamped). Either way **the secret is "trimmed"** — it
never reaches the tool. A tool that requires a credential therefore fails, which is the
correct, intended outcome off Orkes.

## How Orkes resolves the references

(Orkes-Conductor machinery, used as-is; absent in OSS Conductor.)

- **In-process tasks** (`LLM_CHAT_COMPLETE`, MCP, HTTP): substituted in memory immediately
  before execution, then reverted before persisting. Plaintext lives one execution only.
- **External workers** (SIMPLE tasks): substituted into the **poll response** only, scoped
  to the task's `_createdBy` (auto-stamped from `workflow.createdBy` when `securityEnabled=true`).
  Persisted input keeps the reference.
- Substitution walks nested maps/lists, so `__resolved_credentials__: { NAME: "${workflow.secrets.NAME}" }`
  resolves.
- Scope is **per-org**, not per-user (no per-user column in the secret store).

## What the compiler stamps (embedded only)

1. **LLM keys** — `AgentChatCompleteTaskMapper` stamps `apiKey = "${workflow.secrets.<PROVIDER_KEY>}"`
   (provider→env-var via `LlmProviderEnv`). `AgentspanAIModelProvider` reads the resolved key
   from task input. Only the required key is stamped; optional base-url / Gemini project id are
   not (Orkes hard-fails on a missing reference). Standalone falls back to `System.getenv`.
2. **MCP / HTTP headers** — `ToolCompiler.rewriteCredentialPlaceholders` rewrites `${NAME}` to
   `${workflow.secrets.NAME}`. These run in-process, so Orkes substitutes before the call.
3. **SDK worker-tool secrets** — each SIMPLE task gets
   `inputParameters.__resolved_credentials__ = { NAME: "${workflow.secrets.NAME}" }`. The dynamic
   GraalJS enrich script injects it from a `workerCredCfg` map; `compileFrameworkPassthrough` and
   `compilePrefillTasks` stamp it directly. Names come from `AgentCompiler.collectToolCredentials`
   (per-tool, with agent-level fallback). HTTP/MCP excluded — their secrets travel as headers.

## SDK contract (all languages, unchanged)

The worker reads `__resolved_credentials__` from task input, injects the values into the env /
credential context, and strips the key before invoking the tool.

## Sequence (embedded worker tool)

```mermaid
sequenceDiagram
    autonumber
    participant Starter
    participant Orkes as Orkes-Conductor
    participant Worker as SDK Worker
    participant Store as Secret Store (org-scoped)

    Starter->>Orkes: startWorkflow (createdBy/org set)
    Note over Orkes: task input carries __resolved_credentials__:{NAME:"${workflow.secrets.NAME}"}
    Worker->>Orkes: poll task
    Orkes->>Store: getSecret(NAME) for _createdBy's org
    Store-->>Orkes: value
    Orkes-->>Worker: task (input now resolved; persisted copy keeps the reference)
    Worker->>Worker: read __resolved_credentials__, inject env, strip key, run tool
```

## History (why this shape)

The branch tried four other mechanisms first; all are removed:

1. **Status-listener token mint** — Orkes doesn't persist a listener's workflow mutations; token lost.
2. **`AGENTSPAN_MINT_TOKEN` system task** — visible distracting node; still a bespoke token.
3. **`/api/workers/secrets` pull endpoint** — special endpoint + SDK fetcher in four languages.
4. **`WorkerSecretPollAdvice` poll-time injection** — only works when agentspan owns the poll path;
   in a real Orkes deployment the host serves the poll, so it never ran.

Iteration 5 (this doc) drops all of it: stamp references, let Orkes resolve. The host is the
authority; AgentSpan resolves nothing.

## Removed

`CredentialResolutionService`, `CredentialStoreProvider` SPI, `model/credentials/*`,
`CredentialAwareMcpService` (upstream `MCPService` takes over), `CredentialAwareHttpTask(+Config)`,
`WorkerSecretPollAdvice`, `SecretController` (`/api/secrets`), `WorkerController`
(`/api/workers/secrets`), `AgentspanMintTokenTask`, `ExecutionTokenService`, `KnownProviderEnvVars`,
the standalone store (`EncryptedDbCredentialStoreProvider`, `MasterKeyConfig`, `CredentialEnvSeeder`,
`CredentialSchemaMigrator`, `CredentialDataSourceConfig`, `schema-credentials*.sql`), the SDK
credential fetchers, the `agentspan_tool_credentials` / `agentspan_workflow_credentials` def
metadata, and all associated tests.

## Tests

- `ToolCompilerWorkerCredTest` — per-tool refs (embedded on/off), HTTP/MCP excluded, agent-level
  fallback, dynamic variant, plus a GraalJS-executed test asserting the built SIMPLE task carries
  `__resolved_credentials__`.
- `AgentChatCompleteTaskMapperTest` — embedded stamps the `apiKey` reference per provider; standalone doesn't.
- `AgentspanAIModelProviderTest` — builds a model from the resolved `apiKey`; ignores an unresolved placeholder.
- `AgentCompilerTest.testStampsWorkerCredentialsWhenEmbedded` — end-to-end compile carries the
  reference when embedded, absent when standalone.

Per project rule, each behavior was made to fail first before confirming it passes.

### e2e: the OSS trim is validated, not worked around

The e2e suites run against the standalone server (OSS Conductor, `agentspan.embedded=false`),
so there is no secret backend. The credential e2e tests therefore assert the **trim** directly
rather than injecting secret values (which is impossible here):

- A tool needing **no** credential runs and its task **COMPLETES**.
- A tool **requiring** a credential **FAILS** because the secret is trimmed — this expected
  failure *is* the assertion. The tests also prove the secret was genuinely not delivered (the
  tool's success marker never appears) and that an OS env var of the same name is not a silent
  fallback (tools read via the SDK credential accessor — `get_secret` / `getCredential` /
  `ctx.getCredentialOrNull` — which never consults `os.environ`).
- `FAILED` is accepted alongside the terminal variants: with the in-process credential
  machinery removed, a missing credential now surfaces as an ordinary tool exception.

Suites: `sdk/python/e2e/test_suite2_tool_calling.py`, `sdk/typescript/tests/e2e/test_suite2_tool_calling.test.ts`,
`sdk/java/e2e/Suite2ToolCallingCredentials.java`, `sdk/csharp/tests/AgentspanE2eTests/Suite2_ToolCalling.cs`.
The old set/update-and-read lifecycle steps and the `agentspan credentials` CLI command were removed.
