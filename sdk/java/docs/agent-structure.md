# Agent — Field Reference

`Agent` is the declarative configuration you build with `Agent.builder()`. Each field
below lists its builder method, the JSON key it serializes to, and any behavior notes.

## Fields

| Field | Builder method | JSON key | Notes |
|---|---|---|---|
| `name` | `name(String)` | `name` | Required. Pattern `^[a-zA-Z_][a-zA-Z0-9_-]*$`. |
| `model` | `model(String)` | `model` | `"provider/model"` format. Omitted for external agents. |
| `instructions` | `instructions(String)` | `instructions` | System prompt. Overridden by `instructionsTemplate` if set. |
| `instructionsTemplate` | `instructionsTemplate(PromptTemplate)` | `instructions` (structured) | Emitted as a `PromptTemplateRef` map. Takes precedence over plain instructions. |
| `introduction` | `introduction(String)` | `introduction` | Prepended before the first user message in multi-agent discussions. |
| `tools` | `tools(ToolDef...)` | `tools` | List of tool configs. |
| `agents` | `agents(Agent...)` | `agents` | Sub-agents (recursive). Requires a strategy. |
| `strategy` | `strategy(Strategy)` | `strategy` | Emitted only when sub-agents or planner/fallback slots are present. Default `HANDOFF`. |
| `router` | `router(Agent)` | `router` | For `ROUTER` strategy. Nested agent config. |
| `guardrails` | `guardrails(GuardrailDef...)` | `guardrails` | Input/output guardrail configs. |
| `maxTurns` | `maxTurns(int)` | `maxTurns` | Default 25. Emitted only if > 0. |
| `maxTokens` | `maxTokens(int)` | `maxTokens` | LLM token cap. |
| `temperature` | `temperature(double)` | `temperature` | Sampling temperature. |
| `timeoutSeconds` | `timeoutSeconds(int)` | `timeoutSeconds` | Always emitted (including `0`). `0` → server applies its default. |
| `termination` | `termination(TerminationCondition)` | `termination` | e.g. `MaxMessageTermination`, `StopMessageTermination`. |
| `outputType` | `outputType(Class<?>)` | `outputType` | Structured-output class name. |
| `handoffs` | `handoffs(Handoff...)` | `handoffs` | SWARM triggers: `OnTextMention`, `OnToolResult`, `OnCondition`. |
| `allowedTransitions` | `allowedTransitions(Map)` | `allowedTransitions` | SWARM: restricts which agents may transfer to which. |
| `credentials` | `credentials(String...)` | `credentials` | Secret names fetched from the secrets store at runtime. |
| `requiredTools` | `requiredTools(String...)` | `requiredTools` | Tool names that must be called during the run. |
| `metadata` | `metadata(Map)` | `metadata` | Arbitrary key-values stored with the workflow definition. |
| `synthesize` | `synthesize(boolean)` | `synthesize` | Emitted only when `false` (default `true`). |
| `stateful` | `stateful(boolean)` | `stateful` | Emitted as `true` when set. Triggers per-execution domain isolation (`runId`). |
| `sessionId` | `sessionId(String)` | `sessionId` | Emitted inside `agentConfig` and as a top-level `AgentRequest` field. |
| `baseUrl` | `baseUrl(String)` | `baseUrl` | Per-agent LLM provider endpoint override. |
| `includeContents` | `includeContents(String)` | `includeContents` | `"none"` = fresh context; absent = inherit parent context. |
| `thinkingBudgetTokens` | `thinkingBudgetTokens(int)` | `thinkingConfig` | Emitted as `{enabled: true, budgetTokens: N}`. Anthropic extended thinking. |
| `enablePlanning` | `enablePlanning(boolean)` | `enablePlanning` | Prepends a "plan first" preamble to the system prompt. |
| `prefillTools` | `prefillTools(List)` | `prefillTools` | Tool calls executed before the first LLM turn; results injected as context. |
| `planner` | `planner(Agent)` | `planner` | `PLAN_EXECUTE` named slot. |
| `fallback` | `fallback(Agent)` | `fallback` | `PLAN_EXECUTE` fallback agent. |
| `fallbackMaxTurns` | `fallbackMaxTurns(int)` | `fallbackMaxTurns` | `PLAN_EXECUTE` only. |
| `plannerContext` | `plannerContext(List<Context>)` | `plannerContext` | `PLAN_EXECUTE` only. Text/URL context appended to the planner's prompt. Throws at `build()` if strategy ≠ `PLAN_EXECUTE`. |
| `localCodeExecution` | `localCodeExecution(boolean)` | `codeExecution` | Emitted as a `CodeExecutionConfig`. Injects a `run_code` worker tool. |
| `allowedLanguages` | `allowedLanguages(List)` | `codeExecution.allowedLanguages` | Default `["python"]`. |
| `codeExecutionTimeout` | `codeExecutionTimeout(int)` | `codeExecution.timeout` | Default 30s. |
| `allowedCommands` | `allowedCommands(List)` | `codeExecution.allowedCommands` | Shell commands permitted during code execution. |
| `cliConfig` | `cliConfig(CliConfig)` | `cliConfig` | Injects a `run_command` worker tool. |
| `gate` | `gate(TextGate)` | `gate` | Sequential pipeline gate: `{type: "text_contains", text, caseSensitive}`. |
| `stopWhenTaskName` | `stopWhen(String)` | `stopWhen` | Emitted as `{taskName: name}`. |
| `callbacks` | `callbacks(CallbackHandler...)` | `callbacks` | Introspected for `before_model`, `after_model`, `before_agent`, `after_agent`. |
| `beforeModelCallback` | `beforeModelCallback(Function)` | `callbacks` (position `before_model`) | Emitted as a callback entry. |
| `afterModelCallback` | `afterModelCallback(Function)` | `callbacks` (position `after_model`) | Emitted as a callback entry. |
| `beforeAgentCallback` | `beforeAgentCallback(Function)` | `callbacks` (position `before_agent`) | Emitted as a callback entry. |
| `afterAgentCallback` | `afterAgentCallback(Function)` | `callbacks` (position `after_agent`) | Emitted as a callback entry. |
| `memory` | `memory(ConversationMemory)` | `memory` | Emitted as `{messages, maxMessages}`. Multi-turn message history. |
| `reasoningEffort` | `reasoningEffort(String)` | `reasoningEffort` | OpenAI reasoning models: `"low"`, `"medium"`, `"high"`. Ignored by other models. |
| `maskedFields` | `maskedFields(String...)` | `maskedFields` | Field names redacted in execution history/UI. |
| `contextWindowBudget` | `contextWindowBudget(int)` | `contextWindowBudget` | Token threshold for proactive context condensation. |
| `framework` | `framework(String)` | _(dispatch key)_ | Selects the serialization path; not emitted as a field. |
| `frameworkConfig` | `frameworkConfig(Map)` | _(merged at top level)_ | For framework agents; entries merged into the output map. |

## Serialization behavior

A few fields serialize non-obviously:

- **Strategy** is emitted only when sub-agents or `PLAN_EXECUTE` named slots (`planner`/`fallback`)
  are present, so a plain single agent does not carry a redundant `"strategy": "handoff"`.
- **Framework dispatch** — `framework` is a dispatch key, not a field. Native agents serialize
  as `{agentConfig}`; framework-backed agents (`"skill"`, `"openai"`, `"google_adk"`) take an
  early-exit path and serialize as `{framework, rawConfig}`, with `frameworkConfig` merged into
  the top level of the output.
- **synthesize** defaults to `true` and is emitted only when `false`.
- **Callbacks** — the four function-typed callbacks and the `callbacks` list all serialize into a
  single `callbacks` list. Function objects are never sent; each becomes a Conductor task
  reference at its position, and the runtime registers the function as a local worker.

## Defaults

| Field | Builder default |
|---|---|
| `strategy` | `HANDOFF` |
| `maxTurns` | `25` |
| `timeoutSeconds` | `0` (→ server default) |
| `codeExecutionTimeout` | `30` seconds |
| `synthesize` | `true` |
| `stateful` | `false` |
| `enablePlanning` | `false` |
| `localCodeExecution` | `false` |
