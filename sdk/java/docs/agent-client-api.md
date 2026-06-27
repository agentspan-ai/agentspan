# AgentClient — Control-Plane API Reference

`AgentClient` is the Java SDK's interface to the Agentspan server's proprietary agent control-plane (`/api/agent/*`). Strictly scoped to five endpoints — compile, deploy, start, status, respond. Standard Conductor endpoints (`/api/workflow/*`, `/api/tasks`, etc.) are handled by the Conductor SDK's own typed clients (`WorkflowClient`, `TaskClient`, `MetadataClient`).

Every request goes through the shared `ConductorClient`'s native HTTP + auth + serialization layer. No hand-rolled HTTP. `ConductorClientException` is mapped to agentspan's `AgentAPIException` / `AgentNotFoundException`.

## Methods

| Method | HTTP | Java input type | Java return type | Description |
|---|---|---|---|---|
| [`compileAgent`](#compileagent) | `POST /api/agent/compile` | `AgentRequest` | `CompileResponse` | Compile to Conductor workflow def — no side effects |
| [`deployAgent`](#deployagent) | `POST /api/agent/deploy` | `AgentRequest` | `StartResponse` | Register workflow def without starting |
| [`startAgent`](#startagent) | `POST /api/agent/start` | `AgentRequest` | `StartResponse` | Compile + register + start execution |
| [`getAgentStatus`](#getagentstatus) | `GET /api/agent/{id}/status` | path: `executionId` | `AgentStatusResponse` | Poll execution status; includes HITL pending-tool |
| [`respond`](#respond) | `POST /api/agent/{id}/respond` | `RespondBody` | `void` | Resume a paused HITL task |

---

## AgentRequest

Input to `compileAgent`, `deployAgent`, and `startAgent`. Holds a single `Agent` field — no `agentConfig`/`rawConfig` duplication. A custom `Serializer` writes the correct JSON shape based on the `Framework` discriminator.

```java
// Native agent
AgentRequest.nativeAgent(agent).build()

// Framework-backed agent — Framework enum, not a String
AgentRequest.frameworkAgent(Framework.OPENAI, agent).build()
AgentRequest.frameworkAgent(Framework.LANGCHAIN, agent).build()

// With execution fields (for /start only)
AgentRequest.nativeAgent(agent)
    .prompt("What is the capital of France?")
    .sessionId("session-abc")
    .runId("a1b2c3...")   // per-execution domain UUID for stateful agents
    .staticPlan(plan)     // Plan — Serializer calls plan.toJson() internally
    .build()
```

**`AgentRequest.Serializer` wire output:**

| When | JSON emitted |
|---|---|
| `framework == null` (native) | `"agentConfig": AgentConfigSerializer.serialize(agent)` |
| `framework != null` (framework-backed) | `"framework": fw.wireValue(), "rawConfig": AgentConfigSerializer.serialize(agent)` |

**Field mapping to server `StartRequest`:**

| `AgentRequest` field | Java type | JSON key(s) written by Serializer | Server `StartRequest` field | Used by |
|---|---|---|---|---|
| `agent` | `Agent` | `"agentConfig"` or `"rawConfig"` (see above) | `agentConfig` / `rawConfig` | all |
| `framework` | `Framework` | `"framework"` (only when non-null) | `framework` | framework agents |
| `prompt` | `String` | `"prompt"` | `prompt` | start only |
| `sessionId` | `String` | `"sessionId"` | `sessionId` | start (stateful) |
| `runId` | `String` | `"runId"` | `runId` | start (stateful isolation) |
| `staticPlan` | `Plan` | `"static_plan"` (Serializer calls `plan.toJson()`) | `staticPlan` (`@JsonProperty("static_plan")`) | start (PLAN_EXECUTE) |
| `media` | `List<String>` | `"media"` | `media` | start (multi-modal) |
| `context` | `Map<String,Object>` | `"context"` | `context` | start |
| `idempotencyKey` | `String` | `"idempotencyKey"` | `idempotencyKey` | start |
| `credentials` | `List<String>` | `"credentials"` | `credentials` | compile / start |
| `timeoutSeconds` | `Integer` | `"timeoutSeconds"` | `timeoutSeconds` | compile / start |

Null fields are never written — the `Serializer` uses explicit null-checks, not `@JsonInclude`.

**`Framework` enum** — all seven values map 1-to-1 with the server's normalizer registry:

| Enum constant | Wire value | Server normalizer |
|---|---|---|
| `Framework.OPENAI` | `"openai"` | `OpenAINormalizer` |
| `Framework.GOOGLE_ADK` | `"google_adk"` | `GoogleADKNormalizer` |
| `Framework.LANGCHAIN` | `"langchain"` | `LangChainNormalizer` |
| `Framework.LANGGRAPH` | `"langgraph"` | `LangGraphNormalizer` |
| `Framework.SKILL` | `"skill"` | `SkillNormalizer` |
| `Framework.VERCEL_AI` | `"vercel_ai"` | `VercelAINormalizer` |
| `Framework.CLAUDE_AGENT_SDK` | `"claude_agent_sdk"` | `ClaudeAgentSdkNormalizer` |

`AgentRuntime` resolves `agent.getFramework()` → `Framework` via `Framework.of(String)` (returns `Optional.empty()` for unrecognised strings, routing them through the native path).

**Structural proof — `static_plan` key:**
The server field is `staticPlan` annotated `@JsonProperty("static_plan")`. The `Serializer` writes `gen.writeObjectField("static_plan", ...)` — both sides agree on the JSON key.

---

## RespondBody

Input to `respond`. Provides factory methods for the three common patterns; arbitrary extra fields are flattened to the top level via `@JsonAnyGetter`.

```java
RespondBody.approve()                  // { "approved": true }
RespondBody.approve("Looks good")      // { "approved": true, "reason": "Looks good" }
RespondBody.reject("Needs review")     // { "approved": false, "reason": "Needs review" }
RespondBody.of(Map.of("selected", "writer"))  // { "selected": "writer" }  ← MANUAL strategy
```

**Used by `AgentHandle`:**

| `AgentHandle` method | `RespondBody` factory | Wire JSON |
|---|---|---|
| `handle.approve()` | `RespondBody.approve()` | `{ "approved": true }` |
| `handle.approve(comment)` | `RespondBody.approve(comment)` | `{ "approved": true, "reason": "..." }` |
| `handle.reject(reason)` | `RespondBody.reject(reason)` | `{ "approved": false, "reason": "..." }` |
| `handle.respond(map)` | `RespondBody.of(map)` | the map at the top level |

---

## compileAgent

Compile an agent into a Conductor workflow definition. No workflow is registered or executed.

Used by `AgentRuntime.plan(agent)`.

**HTTP:** `POST /api/agent/compile`

### Request body — `AgentRequest`

```java
// AgentRuntime builds this via agentRequest(agent):
AgentRequest.nativeAgent(agent).build()
// or, for framework agents — uses Framework enum, not a raw String:
AgentRequest.frameworkAgent(Framework.OPENAI, agent).build()
```

Native agent wire shape (produced by `AgentRequest.Serializer` calling `AgentConfigSerializer.serialize(agent)`):
```json
{ "agentConfig": { "name": "my_agent", "model": "openai/gpt-4o-mini", "strategy": "handoff", ... } }
```

Framework agent wire shape:
```json
{ "framework": "openai", "rawConfig": { "name": "my_agent", "model": "openai/gpt-4o-mini", "tools": [...] } }
```

### Response — `CompileResponse`

```json
{ "workflowDef": { "name": "my_agent", "version": 1, "tasks": [...] }, "requiredWorkers": ["my_tool_a"] }
```

| Field | Getter | Type | Description |
|---|---|---|---|
| `workflowDef` | `getWorkflowDef()` | `Map<String,Object>` | Full Conductor workflow definition. |
| `requiredWorkers` | `getRequiredWorkers()` | `List<String>` | Task type names the SDK must register local workers for. |

**How the SDK uses it:** `AgentRuntime.plan(agent)` returns the `CompileResponse` directly.

---

## deployAgent

Compile and register the workflow definition on the server without starting an execution. Idempotent.

Used by `AgentRuntime.deploy(Agent...)`.

**HTTP:** `POST /api/agent/deploy`

### Request body — `AgentRequest`

Same as `compileAgent` — agent definition only, no `prompt`.

### Response — `StartResponse`

```json
{ "agentName": "my_agent", "requiredWorkers": ["my_tool_a"] }
```

| Field | Getter | Type | Description |
|---|---|---|---|
| `agentName` | `getAgentName()` | `String` | The registered workflow name on the server. |
| `requiredWorkers` | `getRequiredWorkers()` | `List<String>` | Task type names the SDK must have workers running for. |
| `executionId` | `getExecutionId()` | `String` | Always `null` for deploy — no execution was started. |

**How the SDK uses it:** `AgentRuntime.deploy()` reads `resp.getAgentName()` and wraps it in `DeploymentInfo`.

---

## startAgent

Compile, register, and start a workflow execution in one call.

Used by `AgentRuntime.startAsync(agent, prompt, plan)`.

**HTTP:** `POST /api/agent/start`

### Request body — `AgentRequest`

```json
{
  "agentConfig": { ... },
  "prompt": "What is the capital of France?",
  "sessionId": "session-abc",
  "runId": "a1b2c3d4e5f6...",
  "static_plan": { "steps": [...] }
}
```

### Response — `StartResponse`

```json
{ "executionId": "a3f92b1c-8e4d-4b7a-9c2e-1d5f3a8e6b02", "agentName": "my_agent", "requiredWorkers": ["my_tool_a"] }
```

| Field | Getter | Type | Description |
|---|---|---|---|
| `executionId` | `getExecutionId()` | `String` | Conductor workflow ID. `@JsonAlias` handles legacy keys (`workflowId`, `id`, `correlationId`). |
| `agentName` | `getAgentName()` | `String` | The registered workflow name. |
| `requiredWorkers` | `getRequiredWorkers()` | `List<String>` | Task type names the SDK must have workers polling before the agent can progress. |

**How the SDK uses it:** `AgentRuntime.startAsync()` reads `response.getExecutionId()` and passes it to `new AgentHandle(executionId, agentClient, workflowClient)`.

---

## getAgentStatus

Poll the current status of a running or completed execution.

Used by `AgentHandle.waitForResult()` and `AgentHandle.waitUntilWaiting()`.

**HTTP:** `GET /api/agent/{executionId}/status`

### Response — `AgentStatusResponse`

```json
{ "executionId": "...", "status": "COMPLETED", "isComplete": true, "isRunning": false, "output": { ... } }
```

HITL paused:
```json
{ "status": "RUNNING", "isWaiting": true, "pendingTool": { "taskRefName": "...", "tool_name": "...", "parameters": { ... } } }
```

**`AgentStatusResponse` fields:**

| JSON field | Getter | Type | Source | Description |
|---|---|---|---|---|
| `executionId` | `getExecutionId()` | `String` | path param | — |
| `status` | `getStatus()` | `String` | `workflow.getStatus().name()` | `RUNNING`, `COMPLETED`, `FAILED`, `TERMINATED`, `TIMED_OUT`, `PAUSED` |
| `isComplete` | `isComplete()` | `boolean` | `workflow.getStatus().isTerminal()` | `true` for all terminal statuses |
| `isRunning` | `isRunning()` | `boolean` | `status == RUNNING` | — |
| `output` | `getOutput()` | `Map<String,Object>` | `workflow.getOutput()` | Only present when `isComplete() == true` |
| `reasonForIncompletion` | `getReasonForIncompletion()` | `String` | `workflow.getReasonForIncompletion()` | Only present on non-COMPLETED terminal status |
| `isWaiting` | `isWaiting()` | `boolean` | HUMAN task IN_PROGRESS | `true` when a HITL task is paused |
| `pendingTool` | `getPendingTool()` | `PendingTool` | HUMAN task inputData | Only when `isWaiting() == true` |

**`PendingTool` fields:**

| JSON field | Getter | Type | Description |
|---|---|---|---|
| `taskRefName` | `getTaskRefName()` | `String` | Conductor task reference name. |
| `tool_name` | `getToolName()` | `String` | Logical tool name shown to the human. |
| `parameters` | `getParameters()` | `Map<String,Object>` | Args the agent passed to the tool. |
| `response_schema` | `getResponseSchema()` | `Object` | JSON Schema the response must conform to (optional). |
| `response_ui_schema` | `getResponseUiSchema()` | `Object` | UI rendering hints (optional). |

---

## respond

Resume a paused HITL execution.

Used by `AgentHandle.approve()`, `.reject()`, `.respond(Map)` and `AgentStream.approve()`, `.reject()`.

**HTTP:** `POST /api/agent/{executionId}/respond`

### Request body — `RespondBody`

```json
{ "approved": true }
{ "approved": false, "reason": "Needs review" }
{ "selected": "writer" }
```

### Response

`void` — returns nothing. Throws `AgentAPIException` if no pending HUMAN task exists.

---

## WorkflowClient usage

Raw workflow data (`GET /api/workflow/{id}`) is fetched via the standard Conductor `WorkflowClient` — not `AgentClient`. `AgentClient` owns only `/api/agent/*`.

`WorkflowClient.getWorkflow(id, true)` is called inside `AgentHandle.buildResult()` **once**, after `getAgentStatus` returns terminal, to walk the typed `Workflow`/`Task` objects and compute:

- **Token usage** — `LLM_CHAT_COMPLETE` task `outputData`: `promptTokens`, `completionTokens`, `tokenUsed` → `AgentResult.getTokenUsage()`
- **Tool calls** — worker tasks whose `referenceTaskName` starts with `call_` → `AgentResult.getToolCalls()`

Fires automatically inside `run()` / `waitForResult()`. Callers never invoke it directly.

---

## AgentConfig (request field)

The agent definition serialized under the `agentConfig` key by `AgentConfigSerializer`.

| Field | Type | Description |
|---|---|---|
| `name` | `String` | Agent/workflow name. |
| `model` | `String` | `"provider/model"` e.g. `"openai/gpt-4o-mini"`. |
| `instructions` | `String \| Object` | System prompt or `PromptTemplateRef`. |
| `tools` | `List<ToolConfig>` | Tool definitions. |
| `agents` | `List<AgentConfig>` | Sub-agents (for multi-agent strategies). |
| `strategy` | `String` | `"handoff"` (default), `"sequential"`, `"parallel"`, `"router"`, `"swarm"`, `"round_robin"`, `"random"`, `"plan_execute"`, `"manual"`. |
| `router` | `AgentConfig \| WorkerRef` | For `"router"` strategy. |
| `guardrails` | `List<GuardrailConfig>` | Input/output guardrails. |
| `maxTurns` | `int` | Default `100`. |
| `maxTokens` | `Integer` | LLM `max_tokens`. |
| `temperature` | `Double` | LLM temperature. |
| `timeoutSeconds` | `int` | Execution timeout. |
| `credentials` | `List<String>` | Credential names injected at runtime. |
| `outputType` | `OutputTypeConfig` | Structured output definition. |
| `termination` | `TerminationConfig` | Early termination condition. |
| `handoffs` | `List<HandoffConfig>` | Swarm handoff triggers. |
| `callbacks` | `List<CallbackConfig>` | Before/after model callbacks. |
| `codeExecution` | `CodeExecutionConfig` | Local code execution settings. |
| `cliConfig` | `CliConfig` | CLI command execution settings. |
| `planner` | `AgentConfig` | `PLAN_EXECUTE`: agent that produces the plan. |
| `fallback` | `AgentConfig` | `PLAN_EXECUTE`: agent used when the plan fails. |
| `plannerContext` | `List<Map>` | `PLAN_EXECUTE`: text/URL context appended to the planner's prompt. |
| `synthesize` | `Boolean` | Append a synthesis step after parallel sub-agents. |
| `includeContents` | `String` | `"none"` = fresh context; absent = inherit parent context. |
| `baseUrl` | `String` | Per-agent LLM provider base URL override. |
| `metadata` | `Map<String,Object>` | Arbitrary metadata stored with the workflow definition. |
| `framework` | `String` | Framework ID — set by SDK bridges, not by callers directly. |

### ToolConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `String` | | Tool name shown to the LLM. |
| `description` | `String` | | Tool description. |
| `inputSchema` | `Map<String,Object>` | | JSON Schema for tool parameters. |
| `outputSchema` | `Map<String,Object>` | | JSON Schema for tool return value. |
| `toolType` | `String` | `"worker"` | `"worker"`, `"http"`, `"mcp"`, `"human"`, `"generate_image"`, `"generate_audio"`, `"generate_pdf"`, `"rag_search"`, `"pull_workflow_messages"`. |
| `approvalRequired` | `boolean` | `false` | Pause for human approval before executing. |
| `timeoutSeconds` | `Integer` | | Per-tool execution timeout. |
| `maxCalls` | `Integer` | | Maximum invocations per run. |
| `config` | `Map<String,Object>` | | Type-specific config: `url`/`method`/`headers` for HTTP; `server_url` for MCP. |
| `guardrails` | `List<GuardrailConfig>` | | Tool-level guardrails. |
| `stateful` | `boolean` | `false` | Register worker under a per-execution domain (prevents cross-instance task stealing). |
