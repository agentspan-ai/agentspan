# Agent JSON Schema

[`agent-schema.json`](agent-schema.json) is the canonical wire contract for the agent
configuration that every SDK serializes and sends to the server. SDKs POST it under the
`agentConfig` key of the start/compile request; the server deserializes it into its
`AgentConfig` model and compiles it into a Conductor workflow.

- **Format:** JSON Schema Draft 2020-12.
- **Convention:** camelCase keys; absent = unset (`@JsonInclude(NON_NULL)` server-side).
- **Recursive:** `agents`, `planner`, `fallback`, and `router` nest a full agent config (`$ref: "#"`).
- **Strictness:** `additionalProperties: false` at the root, so the schema is the *complete*
  set of recognized top-level keys.

## What the schema is derived from

The server's `AgentConfig` is the canonical target — both SDKs serialize *to* it. The schema
is the reconciliation of three sources:

| Source | File |
|---|---|
| Server model (deserialization target) | `server/conductor-agentspan/src/main/java/dev/agentspan/runtime/model/AgentConfig.java` (+ nested `*Config` models) |
| Java SDK emit | `sdk/java/src/main/java/org/conductoross/conductor/ai/internal/AgentConfigSerializer.java` |
| Python SDK emit | `sdk/python/src/agentspan/agents/config_serializer.py` |

## Proof of correctness

The schema is correct iff it is **sound** (every key it declares is server-recognized or
explicitly tolerated), **complete** (every key either SDK can emit is permitted), and
**type-consistent** (declared types match the server field and both SDK emit types). Each was
verified in three rounds.

### Round 1 — static inventory

Every field of the server `AgentConfig` and its nested models (`ToolConfig`, `GuardrailConfig`,
`MemoryConfig`, `TerminationConfig`, `HandoffConfig`, `CallbackConfig`, `CodeExecutionConfig`,
`CliConfig`, `ThinkingConfig`, `PrefillToolCallConfig`, `OutputTypeConfig`, `WorkerRef`) was
inventoried with its JSON key and type, alongside the exact set of keys each SDK serializer
emits. The server uses Spring's default Jackson config — **no `FAIL_ON_UNKNOWN_PROPERTIES`** —
so unknown keys are ignored, never rejected. The schema is intentionally *stricter* than the
server (closed `additionalProperties`) to serve as a precise contract.

### Round 2 — discrepancy verification against source

Cross-source differences were confirmed by reading the source directly (not summaries):

| Item | Finding | Schema decision |
|---|---|---|
| guardrail `onFail` | Closed enum `retry \| raise \| fix \| human` — Java `OnFail` enum, Python `_VALID_ON_FAIL`, and the server field comment **all agree**. | enum on `onFail` |
| `strategy` | Python emits `strategy: null` for a single agent (`config_serializer.py:91`); Java omits it. | `type: ["string","null"]`, enum includes `null` |
| `sessionId` | Java emits it **inside** `agentConfig` (`AgentConfigSerializer.java:259`); the server `AgentConfig` has no such field and reads it from the request wrapper. | permitted optional key |
| `planSource` | Python emits it in `agentConfig` (`config_serializer.py:240`); the Java SDK sends the static plan via the wrapper's `static_plan`. Server `AgentConfig` has `planSource`. | permitted optional `object` |
| `reasoningEffort` | Values `minimal \| low \| medium \| high` (`agent.py:515`). | enum |

### Round 3 — empirical conformance

A maximal agent was serialized by **each** SDK and validated against the schema with a Draft
2020-12 validator, then negative mutations were checked, then the result was compiled on a live
server:

| Check | Result |
|---|---|
| Schema is a well-formed Draft 2020-12 schema | ✅ |
| **Python** maximal agent (21 keys) validates | ✅ |
| **Java** maximal agent (29 keys; exercises `memory`, `gate`, `termination`, `thinkingConfig`, `codeExecution`, `guardrails`, `tools`, `agents`, `handoffs`) validates | ✅ |
| Negative (make-fail): unknown key, bad `reasoningEffort`, bad `strategy`, wrong `maxTurns` type, missing `name`, bad guardrail `onFail` — **all rejected** | ✅ |
| Java-emitted, schema-valid config compiles on the live server (`POST /agent/compile` → HTTP 200) | ✅ |

The negative checks establish that the schema has *teeth* — it is not vacuously permissive — and
the live compile establishes that a schema-valid document is genuinely accepted by the server.

## Top-level field correspondence

| Schema property | Type | Server `AgentConfig` | Java emit | Python emit |
|---|---|---|---|---|
| `name` | string (required) | ✅ | ✅ | ✅ |
| `description` | string | ✅ | — | — (platform-set) |
| `model` | string\|null | ✅ | ✅ | ✅ |
| `external` | boolean | ✅ | ✅ | ✅ |
| `baseUrl` | string | ✅ | ✅ | ✅ |
| `instructions` | string\|object\|null | ✅ | ✅ | ✅ |
| `introduction` | string | ✅ | ✅ | ✅ |
| `tools` | array→`tool` | ✅ | ✅ | ✅ |
| `agents` | array→`#` | ✅ | ✅ | ✅ |
| `strategy` | string\|null (enum) | ✅ | ✅ | ✅ |
| `router` | `#`\|`workerRef` | ✅ | ✅ | ✅ |
| `guardrails` | array→`guardrail` | ✅ | ✅ | ✅ |
| `maxTurns` | integer | ✅ | ✅ | ✅ |
| `maxTokens` | integer | ✅ | ✅ | ✅ |
| `temperature` | number | ✅ | ✅ | ✅ |
| `timeoutSeconds` | integer | ✅ | ✅ | ✅ |
| `reasoningEffort` | string (enum) | ✅ | ✅ | ✅ |
| `contextWindowBudget` | integer | ✅ | ✅ | ✅ |
| `thinkingConfig` | `thinkingConfig` | ✅ | ✅ | ✅ |
| `memory` | `memory` | ✅ | ✅ | ✅ |
| `termination` | `termination` | ✅ | ✅ | ✅ |
| `outputType` | `outputType` | ✅ | ✅ | ✅ |
| `handoffs` | array→`handoff` | ✅ | ✅ | ✅ |
| `allowedTransitions` | object | ✅ | ✅ | ✅ |
| `callbacks` | array→`callback` | ✅ | ✅ | ✅ |
| `gate` | `gate` | ✅ | ✅ | ✅ |
| `stopWhen` | `workerRef` | ✅ | ✅ | ✅ |
| `enablePlanning` | boolean | ✅ | ✅ | ✅ |
| `planner` | `#` | ✅ | ✅ | ✅ |
| `fallback` | `#` | ✅ | ✅ | ✅ |
| `fallbackMaxTurns` | integer | ✅ | ✅ | ✅ |
| `plannerContext` | array→`plannerContextEntry` | ✅ | ✅ | ✅ |
| `planSource` | object | ✅ | — (via wrapper) | ✅ |
| `synthesize` | boolean | ✅ | ✅ | ✅ |
| `stateful` | boolean | — (domain isolation) | ✅ | ✅ |
| `sessionId` | string | — (read from wrapper) | ✅ | — (sent in wrapper) |
| `includeContents` | string | ✅ | ✅ | ✅ |
| `requiredTools` | array<string> | ✅ | ✅ | ✅ |
| `prefillTools` | array→`prefillTool` | ✅ | ✅ | ✅ |
| `credentials` | array<string> | ✅ | ✅ | ✅ |
| `metadata` | object | ✅ | ✅ | ✅ |
| `localCodeExecution` | boolean | — (→ `codeExecution`) | builder flag | builder flag |
| `codeExecution` | `codeExecution` | ✅ | ✅ | ✅ |
| `cliConfig` | `cliConfig` | ✅ | ✅ | ✅ |
| `maskedFields` | array<string> | ✅ | ✅ | ✅ |

`—` in the server column marks the two keys the server does not model on `AgentConfig`
(`stateful` drives runtime domain isolation; `sessionId` is read from the request wrapper). Both
are permitted by the schema so that Java's output validates.

## Known cross-SDK divergences

These are *correct per the schema* (both forms validate) but worth noting:

- **Static plan channel.** Python places the static plan in `agentConfig.planSource`; the Java SDK
  sends it in the request wrapper as `static_plan`. The server accepts both.
- **Session id channel.** Java echoes `sessionId` into `agentConfig` in addition to the wrapper;
  Python only sends it in the wrapper. The server reads it from the wrapper.
- **Tool retry fields.** The Java serializer may emit `retryCount` / `retryDelaySeconds` /
  `retryPolicy` on a tool. These are not in the server `ToolConfig` model, so the `tool` definition
  keeps `additionalProperties: true`.
- **`cliConfig.workingDir`.** The Java serializer emits `workingDir` inside `cliConfig`; the server
  `CliConfig` model has no such field (it is ignored server-side). The schema includes it so Java
  output validates.

## Reverse verification

As an independent check that the schema is *complete* (the forward pass started from inventories,
which could omit a field), the schema is reverse-engineered back into models and diffed against the
live source by [`generated/generate.py`](generated/generate.py). It emits a Python dataclass
([`generated/agent_config.py`](generated/agent_config.py)) and a Java record
([`generated/AgentConfigModel.java`](generated/AgentConfigModel.java)) **directly from the schema**,
then asserts:

| Check | Result |
|---|---|
| (a) generated dataclass/record fields are field-for-field identical to the schema (root + 16 nested) | ✅ |
| (b) a generated instance serializes to schema-valid JSON | ✅ |
| (c) every server `AgentConfig` field — root **and** all 13 nested models (`ToolConfig`, `GuardrailConfig`, `TerminationConfig`, …) — is present in the schema | ✅ **0 gaps** |

The generated Java record also compiles under `javac`. The only properties the schema carries
beyond the server models are the documented SDK-emitted/tolerated extras: `sessionId`, `stateful`,
`localCodeExecution` (root) and `cliConfig.workingDir` — nothing was missed.

## Scope

The schema describes **native** agent configs. Framework-bridged agents (`openai`, `google_adk`,
`skill`, …) take a different serialization path and are sent as an opaque `rawConfig` under a
`framework` key in the request wrapper; they are out of scope for this schema.
