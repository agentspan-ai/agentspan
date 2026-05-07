# How To Build A Generic Agent Harness

This document describes a generic agent harness: a runtime that lets an AI model plan, call tools, coordinate work, recover from failures, and safely operate across many domains. The design is intentionally not tied to coding. A coding agent is only one profile of the same harness.

The core idea is simple:

> Treat the model as a planner and language interface. Treat the harness as the operating system that validates, authorizes, executes, records, and recovers every side effect.

## 1. The Problem

An agent harness must let a model do useful work in the real world without turning model text into unchecked side effects.

The harness must solve five problems at once:

- **Intent translation:** Convert model-generated tool requests into typed operations.
- **Safety:** Decide what may run, under which policy, with which credentials, and inside which sandbox.
- **Execution:** Run operations across files, APIs, browsers, databases, workflows, humans, devices, and remote systems.
- **State:** Preserve enough context, artifacts, history, and task state to resume correctly.
- **Coordination:** Manage long-running jobs, subagents, approvals, retries, and external events.

The harness should support "almost anything" by making domain-specific work pluggable while keeping validation, policy, execution, persistence, and recovery generic.

## 2. Design Goals

- **Generic capability model:** Files, APIs, databases, browsers, queues, cloud services, workflows, devices, and people should all look like resources operated through tools.
- **Explicit side effects:** Every real-world action must pass through validation, permission, sandbox, execution, persistence, and model-visible result mapping.
- **Provider independence:** Model providers, message formats, tool-call protocols, and streaming shapes should be replaceable.
- **Recoverability:** Interruptions, crashes, provider failures, duplicate events, and partial tool execution should not corrupt the session.
- **Least privilege:** Tools and agents get only the resources, credentials, and policies they need.
- **Human control:** The user can approve, deny, interrupt, inspect, resume, and constrain the agent.
- **Composability:** Tools, plugins, policies, hooks, resource adapters, model providers, and UIs are separate modules.
- **Observability:** Every decision should be explainable after the fact.

Non-goals:

- Letting the model bypass the harness.
- Treating prompts as security boundaries.
- Giving every tool raw access to every credential or resource.
- Assuming a single UI, model provider, or deployment shape.

## 3. First-Principles Foundation

### Actors

- **User:** Sets intent, scope, policy, and approvals.
- **Model:** Plans, reasons, asks for tools, interprets results, and communicates with the user.
- **Harness:** Owns validation, authorization, execution, persistence, recovery, and event routing.
- **Tool provider:** Exposes concrete capabilities such as web search, database query, email send, file edit, or robot command.
- **Resource owner:** Owns a protected system such as a filesystem, SaaS account, cloud account, device, or database.
- **Operator:** Observes production behavior, debugs failures, and maintains policies.

### Irreducible Constraints

- Models can produce invalid, stale, unsafe, or duplicated tool calls.
- Real-world operations can be irreversible.
- Long-running work can outlive the foreground conversation.
- Providers and tools fail partially.
- Credentials and secrets must not enter model-visible context by default.
- The harness must preserve provider-valid message history.
- The user may be absent, headless, interrupted, or offline.
- Plugins and external tools are supply-chain risk.

### Core Principle

The model proposes. The harness disposes.

No operation is safe because the model says it is safe. Safety comes from structured checks, scoped credentials, sandbox enforcement, and durable audit records.

## 4. Assumptions To Validate

These assumptions are reasonable starting points, but they should be tested early because they shape the architecture.

| Assumption | Why It Matters | How To Validate |
|---|---|---|
| Model providers can reliably emit typed tool calls | The harness depends on structured intent, not free-form command parsing | Run replay tests across target providers with malformed and parallel tool calls |
| Most domains can be modeled as resources plus capabilities | This is the core generic abstraction | Implement three unlike adapters, such as filesystem, browser, and database |
| Sandboxing can enforce the promised boundaries | Permission without enforcement is theater | Build adversarial tests for path, network, credential, and process escapes |
| Users will tolerate explicit approval for high-risk actions | Human control is part of safety | Test prompt frequency and quality in real workflows |
| Plugins are necessary for breadth | "Do anything" requires extension beyond built-ins | Start with a small signed plugin format and measure integration friction |
| Durable workflows are needed for long-running work | Some tasks outlive model turns or sessions | Prototype one event-driven, human-approved workflow |

## 5. Key Decisions

The most irreversible decisions should be made deliberately.

### 1. Core Abstraction

What it determines: whether the harness can generalize beyond one domain.

Options:

- **Resource plus capability model:** Generic, policy-friendly, works across domains. Requires careful adapter design.
- **Tool-only model:** Simpler at first. Becomes hard to reason about shared resources, permissions, and conflicts.
- **Domain-specific runtimes:** Best local ergonomics. Fragmented safety and recovery model.

Recommendation: Use resources plus capabilities, with tools as typed operations over resources.

Reversibility: Low.

### 2. Security Boundary

What it determines: whether safety is enforceable or just documented.

Options:

- **Harness-owned permission and sandbox boundary:** Strongest consistency. More implementation work.
- **Delegate safety to tools/plugins:** Faster integration. Unsafe because each extension invents its own policy semantics.
- **Rely on prompting and model instructions:** Easy. Not a security boundary.

Recommendation: Centralize permission and sandbox enforcement in the harness.

Reversibility: Low.

### 3. Persistence Model

What it determines: whether sessions can resume after partial failure.

Options:

- **Append-only event log with compaction records:** Recoverable and auditable. Requires repair logic.
- **Mutable session snapshot only:** Easy to read. Fragile under crashes and streaming partials.
- **External workflow state only:** Durable for workflows, insufficient for model protocol state.

Recommendation: Use an append-only session/event log plus artifact store and explicit compaction records.

Reversibility: Medium.

### 4. Extension Model

What it determines: how the harness grows to new domains.

Options:

- **Trusted plugins with signed or pinned manifests:** Extensible with supply-chain controls. Operational overhead.
- **Local arbitrary scripts:** Flexible. High risk and hard to audit.
- **No plugins, only built-ins:** Safer initially. Cannot support broad "anything" use cases.

Recommendation: Support plugins, but require source policy, namespace isolation, integrity pinning, and explicit trust.

Reversibility: Medium.

### 5. Long-Running Work Model

What it determines: whether the harness can handle real operations rather than only short tool calls.

Options:

- **Task manager plus durable workflow integration:** Handles both local jobs and business workflows. More moving parts.
- **Background promises only:** Simple but weak across restarts.
- **Everything synchronous:** Easy to reason about but unsuitable for real-world work.

Recommendation: Use local task state for short background work and integrate a workflow engine for durable multi-step work.

Reversibility: Medium.

### Production Use Case Review

The design should be validated against real production agent categories, not just abstract tool calls.

| Use Case | Typical Shape | Required Guarantees | Design Implication |
|---|---|---|---|
| Coding and CI repair | Agent reads repo, edits files, runs tests, opens PR | Dirty-worktree safety, exact diffs, reproducible commands, user-owned credentials | Use worktree/container isolation, patch artifacts, command policy, and PR-specific permissions |
| SRE incident response | Agent reads telemetry, diagnoses, may restart or scale services | Read-mostly by default, break-glass controls, correlation IDs, audit, rollback | Separate diagnosis from remediation; require escalation for production writes |
| Security alert triage | Agent enriches alerts, inspects artifacts, may isolate resources | Chain of custody, untrusted input sandbox, no credential leakage, containment approvals | Treat alert payloads as hostile; isolate tools and require high-confidence approvals |
| Customer support | Agent reads tickets/CRM, drafts replies, issues refunds or credits | PII handling, send approval, customer/account scoping, reversible drafts | Draft by default; side-effecting sends/refunds require permission and tenant policy |
| Sales and RevOps | Agent updates CRM, drafts outreach, schedules follow-ups | Rate limits, consent, unsubscribe policy, brand/legal constraints | Add send throttles, CRM scopes, and compliance checks before external messages |
| Data analysis and BI | Agent queries warehouse, builds reports, schedules refresh | Query budget, row limits, PII controls, reproducible lineage | Use read-only warehouse roles, query cost estimates, artifacts, and scheduled workflows |
| ETL and integrations | Workflow syncs systems on a schedule | Idempotency, retries, dedupe, backfill policy, drift detection | Prefer Conductor schedule plus policy-proxied connectors |
| Finance and accounting | Agent prepares invoices, reconciles payments, initiates payouts | Dual approval, segregation of duties, irreversible side-effect control | Enforce multi-party approval and separation between preparer and approver |
| Legal, healthcare, and compliance | Agent summarizes sensitive material or prepares documents | Strict confidentiality, citations, retention, human sign-off | Disable autonomous external side effects; require source provenance and redaction |
| Browser/RPA automation | Agent navigates web UIs, fills forms, submits actions | Screenshot evidence, submit confirmation, anti-phishing controls | Treat submit and sensitive clicks as side effects with UI proof |
| Cloud provisioning | Agent creates resources, deploys infra, rotates config | Cost controls, IAM scoping, plan/apply separation, rollback | Require dry-run/plan artifacts before apply; enforce account and region policy |
| Cloud cost and FinOps | Agent analyzes AWS/GCP/Azure spend, usage, forecasts, budgets, and waste | Correct account scope, read-only access, deterministic math, confidential spend handling | Bundle cloud billing, inventory, utilization, recommendation, and report tools with provider identity guards |
| Content and publishing | Agent creates media, posts publicly, manages campaigns | Brand review, copyright/provenance, external publishing approval | Store provenance, drafts, and approval records before publish |
| Physical devices and robotics | Agent reads sensors or sends actuator commands | Human safety, fail-safe behavior, bounded command set | Use device-specific safety adapter and emergency-stop channel |

Cross-cutting production requirements surfaced by these cases:

- Every action needs an accountable principal, not just an agent ID.
- Every external side effect needs idempotency, rollback, compensation, or explicit irreversibility acknowledgement.
- High-stakes domains need approval policies beyond a single user click.
- Scheduled and autonomous actions need the same policy checks as interactive actions.
- Production use cases require tenant isolation, quotas, rate limits, and audit exports.

## 6. High-Level Architecture

```text
User or API client
  -> Input processor
  -> Conversation engine
  -> Context builder
  -> Model client
  -> Tool call planner loop
  -> Tool execution pipeline
  -> Permission engine
  -> Sandbox and resource managers
  -> Tool adapters and workflow services
  -> Persistence, events, telemetry, and task state
  -> Model-visible tool results
  -> Final response or next turn
```

### Core Services

| Service | Responsibility |
|---|---|
| `ConversationEngine` | Owns turn lifecycle, model calls, tool loops, interrupts, and finalization |
| `ModelProvider` | Normalizes provider-specific requests, streams, retries, fallback, and message formats |
| `ContextBuilder` | Builds provider-valid context from transcript, memory, artifacts, and resource summaries |
| `ToolRegistry` | Loads, namespaces, filters, ranks, and discovers tools |
| `ToolExecutor` | Runs the generic tool execution pipeline |
| `PermissionEngine` | Decides allow, ask, deny, or limited allow for every side effect |
| `PrincipalResolver` | Resolves user, agent, workflow, schedule, service-account, and delegated identities |
| `SandboxManager` | Enforces filesystem, process, network, browser, credential, and resource boundaries |
| `PythonRuntime` | Runs approved Python code in a pinned, resource-limited sandbox for analysis, transformation, tests, and self-evolution proposals |
| `ResourceManager` | Resolves resource IDs, capabilities, snapshots, locks, and access scopes |
| `TaskManager` | Tracks long-running foreground and background jobs |
| `WorkflowEngine` | Coordinates multi-step, durable, event-driven flows; can delegate durable execution to Conductor |
| `WorkflowCompiler` | Converts selected agent plans into durable workflow definitions, deterministic skeletons, and execution inputs |
| `AgentManager` | Spawns and monitors child agents with scoped tools and transcripts |
| `SecretBroker` | Provides credentials to tools without revealing raw secrets to the model |
| `ArtifactStore` | Stores files, reports, datasets, screenshots, diffs, logs, and generated media |
| `PersistenceStore` | Persists transcript, events, decisions, tasks, artifacts, and resumable state |
| `HookRunner` | Executes lifecycle hooks with strict validation, timeout, and policy |
| `PluginManager` | Loads trusted extensions with manifest validation and integrity policy |
| `SkillManager` | Loads operational skills such as Conductor and exposes their capabilities through policy-checked tools |
| `EventBus` | Streams UI events, SDK events, telemetry, task notifications, and workflow signals |
| `BudgetManager` | Enforces token, cost, time, tool-call, concurrency, and side-effect budgets |

### Service Boundary Contracts

These interfaces are the core implementation seams. Keep them stable and make all side effects pass through them.

```ts
type OperationDescriptor = {
  operationId: string;
  principal: Principal;
  toolName: string;
  resources: ResourceRef[];
  capabilities: Capability[];
  environment: "local" | "dev" | "staging" | "production";
  dataClassification: "public" | "internal" | "confidential" | "restricted" | "regulated";
  riskTier: "low" | "medium" | "high" | "critical";
  purpose: string;
  sideEffectPlan?: SideEffectPlan;
};

interface PrincipalResolver {
  resolve(input: PrincipalInput): Promise<Principal>;
  delegate(input: DelegationRequest): Promise<Principal>;
  assertScope(principal: Principal, scope: string): Promise<void>;
}

interface ResourceManager {
  resolve(ref: ResourceRef, principal: Principal): Promise<ResolvedResource>;
  authorizeReference(ref: ResourceRef, principal: Principal): Promise<ResourceRef>;
  snapshot(ref: ResourceRef): Promise<ResourceSnapshot | undefined>;
  lock(ref: ResourceRef, mode: "read" | "write" | "exclusive"): Promise<ResourceLock | undefined>;
}

interface PermissionEngine {
  decide(operation: OperationDescriptor, context: PolicyContext): Promise<PermissionDecision>;
  explain(decision: PermissionDecision): PermissionExplanation;
  replay(decisionId: string, policyVersion: string): Promise<PermissionDecision>;
}

interface SecretBroker {
  resolveHandle(handle: string, principal: Principal, operation: OperationDescriptor): Promise<SecretLease>;
  mintScopedCredential(request: CredentialRequest): Promise<SecretLease>;
  revokeLease(leaseId: string): Promise<void>;
}

interface WorkflowCompiler {
  compile(plan: WorkflowPlan, context: CompileContext): Promise<WorkflowIR>;
  analyze(ir: WorkflowIR, context: PolicyContext): Promise<WorkflowAnalysis>;
  renderConductor(ir: WorkflowIR): Promise<RenderedWorkflowArtifact>;
}

interface ConductorAdapter {
  register(definition: RenderedWorkflowArtifact, decision: PermissionDecision): Promise<WorkflowDefinitionRef>;
  start(request: WorkflowStartRequest, decision: PermissionDecision): Promise<WorkflowExecutionRef>;
  schedule(request: WorkflowSchedule, decision: PermissionDecision): Promise<WorkflowScheduleRef>;
  status(ref: WorkflowExecutionRef): Promise<WorkflowExecutionStatus>;
  signal(request: WorkflowSignalRequest, decision: PermissionDecision): Promise<WorkflowExecutionStatus>;
  manage(request: WorkflowManagementRequest, decision: PermissionDecision): Promise<WorkflowExecutionStatus>;
}
```

Boundary rules:

- `ToolExecutor` may not call a resource adapter until `PermissionEngine` returns an allow or approved limited allow.
- `ConductorAdapter` may not register, start, schedule, signal, or manage workflows without a permission decision.
- `SecretBroker` returns leases to tools and workers, not raw values to model context.
- `WorkflowCompiler.analyze` must produce the `OperationDescriptor` inputs used by `PermissionEngine`.
- All service methods emit audit events with principal, tenant, operation ID, policy version, and trace ID.

## 7. Universal Runtime Model

Everything the agent can touch should be represented with a small set of primitives.

### Resource

A resource is anything the harness can inspect or affect.

Examples:

- File or directory
- URL or web page
- Browser session
- Database table or query endpoint
- API account
- Queue or topic
- Cloud project
- Email thread
- Calendar event
- Repository
- Container or VM
- Document
- Image, audio, or video asset
- Human approval request
- Device or robot
- External workflow execution
- Conductor workflow definition or execution

```ts
type ResourceRef = {
  uri: string;
  kind: string;
  tenantId?: string;
  owner?: string;
  labels?: Record<string, string>;
  sensitivity?: "public" | "internal" | "confidential" | "secret";
};
```

### Principal And Delegation

A principal is the accountable identity behind an action. Production systems need this because actions may be initiated by humans, agents, service accounts, workflows, schedules, or external workers.

```ts
type Principal = {
  id: string;
  kind: "human_user" | "service_account" | "agent" | "workflow_execution" | "scheduled_run" | "external_worker";
  tenantId: string;
  organizationId?: string;
  displayName?: string;
  actingOnBehalfOf?: string;
  scopes: string[];
  delegatedBy?: string;
  delegationReason?: string;
  expiresAt?: number;
  authStrength?: "anonymous" | "session" | "mfa" | "service_token" | "break_glass";
};
```

Principal rules:

- Every permission decision, tool execution, workflow start, schedule fire, and audit event must include a principal.
- Delegated principals must include who delegated authority, why, what scopes were granted, and when the delegation expires.
- Scheduled workflow runs should use a schedule principal that references the owner and policy snapshot, not an unbounded user session token.
- Agent and workflow principals must never gain broader scopes than the user, service account, or policy that created them.
- Cross-tenant resource access is denied unless a managed policy explicitly allows it.

### Capability

A capability is an allowed operation over a resource.

```ts
type Capability =
  | "read"
  | "search"
  | "write"
  | "delete"
  | "execute"
  | "send"
  | "publish"
  | "approve"
  | "admin"
  | "credential_use";
```

### Skill

A skill is a curated operational capability pack. It can include instructions, references, scripts, allowed commands, validation rules, and tool mappings. Skills are loaded by `SkillManager`, filtered by policy, and surfaced to the model only through structured tools or clearly labeled instructions.

Skills are executable policy surfaces. Treat them with the same trust discipline as plugins.

```ts
type SkillDefinition = {
  name: string;
  description: string;
  source: "built_in" | "managed" | "user" | "plugin";
  version?: string;
  path?: string;
  namespace: string;
  integrity?: {
    pinnedVersion?: string;
    commit?: string;
    digest?: string;
    signature?: string;
  };
  requiredEnvironment?: string[];
  allowedCommands?: string[];
  allowedOperations: string[];
  toolMappings: ToolMapping[];
};
```

Skill trust rules:

- Enforce source policy before loading.
- Pin managed or plugin-provided skills by version, commit, digest, or signature.
- Validate path ownership and permissions.
- Validate command allowlists before exposing tool mappings.
- Namespace all skill-provided tools, hooks, and commands.
- Disable and unload all contributed tools immediately when a skill is disabled.

The `conductor` skill is the canonical durable workflow orchestration skill. It provides the operational rules for defining, registering, executing, monitoring, scheduling, managing, and signaling Conductor workflows.

### Tool

A tool is a typed model-facing operation that may use one or more capabilities.

```ts
type ToolDefinition<I, O> = {
  name: string;
  namespace: string;
  description: string;
  inputSchema: JsonSchema<I>;
  outputSchema: JsonSchema<O>;
  safety: ToolSafety;
  concurrency: ConcurrencyPolicy;
  timeoutMs: number;
  maxOutputBytes: number;
  validateInput?: (input: I, ctx: ToolContext) => ValidationResult;
  describePermission?: (input: I, ctx: ToolContext) => PermissionDescriptor;
  execute: (input: I, ctx: ToolExecutionContext) => Promise<O>;
};
```

```ts
type ToolSafety = {
  readOnly: boolean;
  destructive: boolean;
  externalSideEffect: boolean;
  usesCredentials: boolean;
  returnsSensitiveData: boolean;
  idempotent: boolean;
  reversible: boolean;
};
```

### Tool Call And Tool Result

```ts
type ToolCall = {
  id: string;
  toolName: string;
  input: unknown;
  modelMessageId: string;
};

type ToolResult = {
  toolCallId: string;
  status: "completed" | "failed" | "denied" | "blocked" | "cancelled";
  content: unknown;
  artifacts?: ArtifactRef[];
  error?: StructuredError;
  redactions?: RedactionRecord[];
};
```

Rules:

- Every model-emitted tool call receives exactly one model-visible tool result.
- Synthetic failures are valid tool results.
- Permission denials are model-visible tool results.
- Tool exceptions are wrapped; they do not skip result generation.
- Model-visible tool results must never include raw secrets. If a product supports explicit secret reveal, use a separate UI-only, non-durable event outside model context.

### Task

A task represents long-running work.

```ts
type TaskState = {
  id: string;
  kind: "tool" | "agent" | "workflow" | "remote" | "human" | "stream";
  lifecycle: "pending" | "running" | "completed" | "failed" | "cancelled" | "killed";
  executionMode: "foreground" | "background";
  description: string;
  ownerAgentId?: string;
  toolCallId?: string;
  resourceRefs: ResourceRef[];
  outputArtifact?: ArtifactRef;
  startedAt: number;
  endedAt?: number;
  notified: boolean;
};
```

Foreground/background is placement, not lifecycle. A running foreground task may be moved to background by flipping `executionMode`, not by creating a new task.

### Artifact

Artifacts are durable outputs too large, sensitive, or structured for direct model context.

Examples:

- Full command output
- Generated report
- Dataset export
- Web crawl archive
- Screenshot
- Browser recording
- Patch
- Audio or video file
- Workflow execution log

```ts
type ArtifactRef = {
  id: string;
  uri: string;
  mimeType: string;
  sizeBytes: number;
  sensitivity: "public" | "internal" | "confidential" | "secret";
  preview?: string;
  retentionPolicy: string;
};
```

## 8. Message And Event Model

The harness should distinguish durable conversation messages from runtime events.

### Durable Messages

- User messages
- Assistant messages
- Tool-use blocks
- Tool-result blocks
- Synthetic repair messages needed to preserve provider validity
- Compact summaries and replacement records

### Runtime Events

- Token stream deltas
- Tool progress
- Permission prompts
- Task status changes
- Background notifications
- UI-only secret reveal events
- Telemetry spans

Runtime events are not automatically transcript messages. Persist them separately as audit or UI events.

### Conversation Graph

Streaming and parallel tool calls can produce a graph, not a simple linked list.

Rules:

- Store message IDs and parent IDs.
- Preserve provider raw assistant messages for replay.
- Recover sibling assistant fragments and sibling tool results on resume.
- Detect parent-chain cycles and recover the longest valid partial transcript.
- Before every model call, repair the history into a provider-valid message order.

## 9. Conversation Engine

The conversation engine is an async state machine.

```text
receive input
  -> normalize into typed user message or control command
  -> append durable input
  -> build model context
  -> call model
  -> stream assistant output
  -> collect tool calls
  -> execute tool batch
  -> append tool results
  -> repeat while model requests tools
  -> run final-response checks
  -> persist final state
  -> emit final response
```

### Exit Reasons

```ts
type LoopExitReason =
  | "final_response"
  | "max_turns"
  | "interrupted"
  | "model_error"
  | "tool_protocol_error"
  | "blocked_by_policy"
  | "budget_exhausted"
  | "context_exhausted";
```

The engine should return structured final state, not just text.

## 10. Tool Execution Pipeline

Every tool uses the same pipeline.

```text
receive tool call
  -> parse input against schema
  -> run semantic validation
  -> run pre_tool_use hooks
  -> if hooks modified input, re-parse and revalidate
  -> derive permission descriptor from final input
  -> decide permission
  -> if ask, prompt user or fail closed according to mode
  -> allocate sandbox and resource scopes
  -> execute with abort signal, timeout, progress callback, and output cap
  -> classify output sensitivity
  -> map to model-facing result
  -> persist artifacts and audit record
  -> run post_tool_use hooks
  -> return exactly one tool result
```

Critical requirements:

- Hook-mutated input must be validated again.
- Permission must be computed from the final input, not the original input.
- Internal-only fields are stripped before execution.
- Output is classified before display, transcript write, and telemetry.
- Large output is stored as an artifact with a bounded preview.
- Tool execution should not mutate provider-bound assistant messages.

### Idempotency And Compensation

Production side effects need explicit retry semantics.

```ts
type SideEffectPlan = {
  sideEffectId: string;
  idempotencyKey?: string;
  reversible: boolean;
  compensation?: {
    toolName: string;
    input: unknown;
    safeWindowSeconds?: number;
  };
  preconditions: string[];
  postconditions: string[];
  externalReference?: string;
};
```

Rules:

- Every external side effect should have a stable `sideEffectId`.
- Retried operations need an idempotency key or explicit non-idempotent approval.
- Destructive or financial operations need preconditions, postconditions, and a compensation or rollback story.
- If an operation is irreversible, the permission prompt must say so directly.
- Automatic retry is disabled for non-idempotent operations unless the tool declares a safe retry contract.
- Reconciliation workflows should detect whether an ambiguous side effect actually happened before retrying.

## 11. Permission System

The permission system decides whether a tool call may proceed.

### Decision Values

```ts
type PermissionDecision =
  | { type: "allow"; scope: PermissionScope; reason: string }
  | { type: "limited_allow"; scope: PermissionScope; constraints: Constraint[]; reason: string }
  | { type: "ask"; prompt: PermissionPrompt; reason: string }
  | { type: "deny"; reason: string };
```

### Permission Modes

| Mode | Behavior |
|---|---|
| `default` | Ask for side effects unless allowed by policy |
| `read_only` | Allow reads, deny writes and external side effects |
| `plan` | Allow planning and local context reads, deny execution |
| `dont_ask` | Convert unresolved asks to denials before any UI prompt |
| `trusted` | Use broad allow rules, but still enforce hard denies and sandbox |
| `autonomous` | Run within explicit scope, budgets, sandbox, and side-effect policy |
| `break_glass` | Explicitly unsafe; requires strong user confirmation and audit |

### Decision Order

```text
if hard deny rule matches:
  deny
if resource policy denies:
  deny
if tool-specific safety check denies:
  deny
if sandbox cannot enforce required boundary:
  deny or ask for unsafe escalation
if explicit allow rule matches:
  provisional allow
run permission_request hooks
normalize hook result into provisional decision
apply mode policy
if mode is dont_ask and decision is ask:
  deny
if decision is ask and UI prompt is available:
  ask user
if decision is ask and no UI prompt is available:
  deny
return final decision
```

Hard rules:

- Deny rules outrank allow rules.
- A model's explanation never changes the permission decision.
- Headless mode must not hang waiting for a prompt.
- A permission hook cannot bypass final mode policy.
- Prompt text should explain intent, resources, credentials, and expected side effects.

### Production Governance

Permission decisions should consider more than the tool name.

```ts
type PermissionDescriptor = {
  principal: Principal;
  resources: ResourceRef[];
  capabilities: Capability[];
  environment: "local" | "dev" | "staging" | "production";
  dataClassification: "public" | "internal" | "confidential" | "restricted" | "regulated";
  riskTier: "low" | "medium" | "high" | "critical";
  purpose: string;
  sideEffectPlan?: SideEffectPlan;
};
```

Production approval policies:

- Low-risk reads can be auto-allowed when scoped.
- Medium-risk writes usually require one approval.
- High-risk production changes require step-up authentication or an explicitly trusted policy path.
- Critical actions such as payments, refunds above threshold, customer deletion, production data export, legal/medical output, or destructive infrastructure changes require multi-party approval.
- Segregation of duties must be enforceable: the same principal should not both prepare and approve high-risk actions.
- Break-glass approvals require reason, expiry, elevated audit, and post-action review.
- Cross-tenant access is denied by default.
- Data residency and retention policy must be checked before moving data across regions or stores.

### Policy Model

Policies should be structured, versioned, and replayable. Avoid burying authorization logic in prompts, hooks, or adapter-specific code.

```ts
type PolicyRule = {
  id: string;
  version: string;
  effect: "allow" | "ask" | "deny" | "limit";
  priority: number;
  match: PolicyMatch;
  constraints?: Constraint[];
  approval?: ApprovalRequirement;
  reason: string;
};

type PolicyMatch = {
  principals?: PrincipalSelector[];
  resourceKinds?: string[];
  resourceUris?: string[];
  capabilities?: Capability[];
  environments?: string[];
  dataClassifications?: string[];
  riskTiers?: string[];
  tools?: string[];
  schedules?: boolean;
};

type ApprovalRequirement = {
  count: number;
  approverScopes: string[];
  requireMfa?: boolean;
  segregationOfDuties?: boolean;
  expiresInSeconds: number;
};
```

Policy evaluation order:

1. Normalize resource references and principal.
2. Evaluate hard deny rules.
3. Evaluate tenant, region, data-classification, and environment rules.
4. Evaluate tool and capability-specific rules.
5. Evaluate schedule/autonomy/workflow-specific rules.
6. Apply allow, ask, deny, or limit.
7. Apply permission mode transforms such as `dont_ask`.
8. Persist the decision with policy version and matched rule IDs.

Policy tests:

- Every managed policy change should include fixture operations that prove allowed, denied, and ask cases.
- Every historical critical incident should become a policy regression test.
- Policy replay should explain whether a past decision would change under a new policy version.

## 12. Sandboxing And Containment

Permissions decide whether an operation is allowed. Sandboxes enforce what it can actually touch.

Sandbox dimensions:

- Filesystem roots and protected paths
- Process execution and child-process cleanup
- Network egress and domain allowlists
- Browser profile isolation
- Database roles and row or schema scope
- Cloud account, project, region, and IAM scope
- API token scope
- Device command scope
- Secret handle scope
- Time, CPU, memory, disk, and output limits

If a sandbox cannot enforce the promised boundary, the harness must downgrade, ask, or deny.

## 13. Resource Adapters

Resource adapters convert generic harness operations into domain-specific execution.

### Adapter Contract

```ts
type ResourceAdapter = {
  kind: string;
  resolve(ref: ResourceRef, ctx: AdapterContext): Promise<ResolvedResource>;
  capabilities(ref: ResourceRef, principal: Principal): Promise<Capability[]>;
  snapshot?(ref: ResourceRef): Promise<ResourceSnapshot>;
  lock?(ref: ResourceRef, mode: "read" | "write"): Promise<ResourceLock>;
  auditLabel(ref: ResourceRef): string;
};
```

### Common Adapters

| Adapter | Use Cases | Key Risks |
|---|---|---|
| Filesystem | Read, write, move, patch files | Path traversal, symlinks, partial writes |
| Process | Shell, scripts, local commands | Destructive commands, credential leakage, hangs |
| HTTP/API | REST, GraphQL, webhooks | External side effects, auth scope, rate limits |
| Browser | Navigation, forms, scraping, screenshots | Phishing, unintended submits, cross-site data |
| Database | Query, export, update | Data loss, injection, privacy, locks |
| Queue/Event | Publish, consume, signal | Duplicate events, poison messages |
| Email/Calendar | Read, draft, send, schedule | Accidental send, private data exposure |
| Cloud | Deploy, inspect, provision | Cost, privilege escalation, regional compliance |
| Cloud Cost and Billing | Cost usage, budgets, forecasts, unit economics | Confidential spend data, wrong account, expensive queries |
| Cloud Asset and IAM | Inventory, IAM inspection, policy analysis | Cross-account leakage, privilege escalation, stale inventory |
| Kubernetes and Containers | Inspect clusters, pods, images, deployments | Production outages, namespace escape, image secrets |
| IaC | Terraform/OpenTofu plans, drift, applies | Destructive applies, state corruption, wrong workspace |
| Observability | Logs, metrics, traces, incidents, dashboards | PII in logs, false confidence from missing data |
| Security | SBOMs, dependency scans, SAST, cloud posture | Sensitive findings, scanner side effects, noisy false positives |
| SCM and Issues | Git, PRs, issues, reviews, release metadata | Credential misuse, accidental merge, leaked diffs |
| Package Registry | Dependency metadata, publish, audit | Supply-chain compromise, accidental publish |
| MCP/App Connector | Discover and call tools from external tool servers or apps | Tool injection, overbroad scopes, untrusted schemas |
| Workflow | Start, pause, retry, signal workflows | Duplicate starts, wrong correlation ID |
| Conductor | Define, register, schedule, start, monitor, retry, and signal durable workflows | Bad workflow definitions, missing workers, wrong profile, duplicate starts, schedule drift |
| Human | Approval, clarification, task handoff | Ambiguous response, timeout |
| Device | Sensor reads, actuator commands | Physical safety, latency, fail-safe behavior |

### Filesystem Handling

Filesystem support is a day-one requirement because almost every useful agent eventually reads or writes artifacts, code, configs, reports, or workflow definitions.

Rules:

- Resolve real paths before permission checks.
- Reject path traversal, symlink escapes, bare repositories, protected config directories, auth stores, and harness runtime directories.
- Require exact old text, patch context, or current snapshot for edits.
- Fail with conflict if the file changed between read and write.
- Write through temp file, flush, rename, and fsync parent directory where supported.
- Preserve permissions and line endings unless explicitly changed.
- Treat binary files as artifacts with metadata and previews, not raw model text.
- Use file locks or worktree/container isolation for parallel write-capable agents.
- Keep before/after snapshots for audit, rollback, and review.
- Scan diffs for secrets before display, transcript write, artifact preview, or PR creation.

## 14. Essential Tool Inventory

Expose stable model-facing tools grouped by capability. Hide internal services and keep high-cardinality provider details behind discovery.

### Core Tools

| Tool | Purpose | Default Permission |
|---|---|---|
| `read_resource` | Read bounded content or metadata from a resource | Allow if scoped |
| `search_resources` | Search files, docs, messages, databases, or indexes | Allow if scoped |
| `write_resource` | Create or replace resource content | Ask |
| `patch_resource` | Apply structured changes with conflict checks | Ask |
| `delete_resource` | Delete or archive a resource | Ask or deny by default |
| `call_api` | Call an external API with structured request | Policy-dependent |
| `query_data` | Query a database or analytical source | Read-only allow if scoped |
| `mutate_data` | Insert, update, or delete records | Ask |
| `browser_action` | Navigate, inspect, click, type, submit | Ask aggressively |
| `run_process` | Run local or remote command | Ask unless read-only and allowlisted |
| `cli_command` | Run a known CLI through a structured profile and parser | Allow only for read-only allowlisted commands |
| `code_index` | Resolve symbols, references, call graph, dependency graph, or test impact | Allow if scoped |
| `git_operation` | Inspect or mutate version-control state | Reads allowed if scoped; branch/commit/push/merge ask |
| `package_operation` | Inspect, install, audit, or publish packages | Reads allowed; install/publish ask |
| `cloud_identity` | Verify current cloud account, project, subscription, principal, and region | Allow if scoped |
| `cloud_cost_query` | Query cost, usage, budgets, forecast, and anomalies | Allow read-only if scoped and bounded |
| `cloud_asset_query` | Query cloud inventory, tags, utilization, and IAM metadata | Allow read-only if scoped |
| `cloud_recommendation` | Fetch or generate rightsizing, commitment, idle resource, or waste recommendations | Allow read-only if scoped |
| `kubernetes_query` | Inspect clusters, namespaces, workloads, events, and resource usage | Allow read-only if scoped |
| `kubernetes_mutate` | Restart, scale, apply, delete, or exec into workloads | Ask; production requires stronger approval |
| `iac_plan` | Generate plan, drift report, or cost estimate for infrastructure changes | Allow or ask depending on state access |
| `iac_apply` | Apply infrastructure changes | Ask; production requires explicit approval and plan binding |
| `observability_query` | Query logs, metrics, traces, alerts, and dashboards | Allow if scoped and redacted |
| `security_scan` | Run dependency, container, secret, SAST, or cloud-posture scans | Allow if scoped; external uploads ask |
| `mcp_list_tools` | Discover tools from an approved MCP/app connector | Allow if connector is scoped |
| `mcp_call_tool` | Call an approved MCP/app tool through policy proxy | Policy-dependent; unknown side effects ask |
| `define_workflow` | Generate or update a durable workflow definition artifact | Ask before registration |
| `register_workflow` | Register a workflow definition in a workflow backend such as Conductor | Ask |
| `start_workflow` | Start a durable workflow | Ask unless safe and idempotent |
| `schedule_workflow` | Create or update a cron-like schedule that starts a workflow | Ask |
| `manage_schedule` | Pause, resume, delete, or inspect workflow schedules | Ask for mutation, allow for read if scoped |
| `workflow_status` | Inspect workflow execution status and failed tasks | Allow if scoped |
| `signal_workflow` | Signal or approve a waiting workflow | Ask |
| `manage_workflow` | Pause, resume, terminate, retry, rerun, skip, or jump workflow execution | Ask; terminate/destructive operations need stronger confirmation |
| `task_status` | Inspect long-running tasks | Allow |
| `task_output` | Read task output artifact | Allow if scoped |
| `cancel_task` | Cancel or kill a task | Ask for external work, allow for own background task |
| `spawn_agent` | Delegate to a child agent | Ask or policy-limited |
| `ask_user` | Request clarification or approval-like input | Allow, rate-limited |
| `memory_read` | Read scoped memory | Allow if scoped |
| `memory_write` | Store durable memory | Ask or policy-dependent |
| `create_artifact` | Save a report, file, image, or dataset | Ask if writes outside session store |

### Discovery Tools

| Tool | Purpose |
|---|---|
| `list_capabilities` | Show available domains and high-level tools |
| `search_tools` | Find deferred tool schemas without bloating model context |
| `describe_resource` | Explain what can be done with a resource |
| `get_policy` | Show active policy constraints in model-safe form |

Do not expose raw secret retrieval, arbitrary credential access, internal event mutation, policy editing, or plugin installation as ordinary model-facing tools.

### Day-One Bundled Tool Pack

A production-ready harness should be useful on day one without requiring every team to write plugins first. Bundle a conservative, well-instrumented default tool pack.

| Category | Tools | Purpose | Default Policy |
|---|---|---|---|
| Resource discovery | `list_capabilities`, `describe_resource`, `search_resources`, `resource_metadata` | Let the model understand what exists and what can be done | Allow scoped reads |
| Filesystem and documents | `read_file`, `list_directory`, `search_files`, `read_document`, `read_pdf`, `read_docx`, `read_xlsx`, `read_image`, `create_artifact`, `patch_file`, `write_file`, `move_file`, `safe_delete` | Inspect and produce durable work products | Reads allowed if scoped; writes ask |
| Code workspace | `git_status`, `git_diff`, `git_log`, `git_blame`, `git_show`, `git_branch`, `git_worktree`, `apply_patch`, `run_tests`, `lint`, `format_check`, `open_pr_draft` | Coding and self-evolution workflows | Reads allowed; writes and PR actions ask |
| Code intelligence | `symbols`, `definition`, `references`, `call_graph`, `dependency_graph`, `test_impact`, `semantic_code_search` | Make coding agents precise across large repos | Allow scoped reads |
| Package managers | `npm`, `pnpm`, `yarn`, `uv`, `pip`, `poetry`, `go`, `cargo`, `mvn`, `gradle`, `dotnet`, `nuget`, `bundler` wrappers | Install, audit, test, build, and inspect dependencies | Inspect/audit allowed; install/update/publish ask |
| Python sandbox | `python_run`, `python_test`, `python_package_info`, `python_artifact` | Data analysis, transformation, validation, local code generation, and test execution | Ask for filesystem/network; no raw secrets |
| Process execution | `run_process`, `background_process`, `process_status`, `process_output`, `kill_process` | Controlled local or remote commands | Ask unless read-only and allowlisted |
| CLI wrappers | `cli_command`, `cli_profile`, `cli_help`, `cli_version`, `cli_json` | Use common operational CLIs without exposing arbitrary shell as the main interface | Read-only allowlist; mutations ask |
| HTTP and APIs | `http_request`, `api_call`, `web_fetch`, `web_search` | Fetch data and call structured APIs | Domain allowlist or ask |
| Browser/RPA | `browser_open`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_submit`, `browser_screenshot` | Web UI workflows and evidence capture | Submit and sensitive clicks ask |
| Data tools | `query_data`, `sample_data`, `profile_data`, `transform_data`, `export_data`, `duckdb_query`, `warehouse_query` | BI, ETL, reports, audits | Read-only scoped; export/mutation ask |
| Cloud identity | `aws_identity`, `gcp_identity`, `azure_identity`, `cloud_scope_guard` | Verify account/project/subscription before doing work | Allow scoped reads |
| Cloud cost | `cloud_cost_query`, `cloud_cost_forecast`, `cloud_budget_status`, `cloud_anomaly_detect`, `cloud_unit_cost_report`, `cloud_commitment_coverage`, `cloud_export_report` | FinOps, spend analysis, forecasting, budget tracking | Read-only scoped; export ask |
| Cloud inventory | `cloud_asset_inventory`, `cloud_tag_coverage`, `cloud_idle_resources`, `cloud_rightsizing_recommendations`, `cloud_pricing_lookup` | Explain spend drivers and produce safe recommendations | Read-only scoped |
| Cloud operations | `cloud_change_plan`, `cloud_apply_change`, `cloud_rollback`, `cloud_quota_status` | Remediation and provisioning | Plan allowed; apply/rollback ask |
| Kubernetes and containers | `kubectl_get`, `kubectl_describe`, `kubectl_logs`, `kubectl_top`, `kubectl_diff`, `helm_list`, `helm_template`, `container_scan` | Cluster and container diagnosis | Reads allowed; apply/exec/delete ask |
| IaC | `terraform_plan`, `terraform_show`, `terraform_state_read`, `terraform_cost_estimate`, `opentofu_plan`, `iac_drift_detect`, `iac_apply` | Infrastructure planning and controlled execution | Plans allowed; state mutation/apply ask |
| Observability | `metrics_query`, `logs_query`, `traces_query`, `alert_search`, `dashboard_snapshot`, `incident_status`, `runbook_search` | SRE, incident, performance, and capacity analysis | Read-only scoped; redaction required |
| Security | `secret_scan`, `sbom_generate`, `dependency_audit`, `container_scan`, `sast_scan`, `cloud_posture_read`, `iam_access_analyze` | Secure coding and cloud/security triage | Reads/scans allowed; external upload or containment ask |
| MCP and app connectors | `mcp_list_tools`, `mcp_call_tool`, `connector_status`, `connector_schema`, `connector_audit` | Extend into approved SaaS, internal tools, and custom systems without shipping every integration in core | Discovery allowed if scoped; calls policy-checked |
| Workflow and schedules | `define_workflow`, `register_workflow`, `start_workflow`, `workflow_status`, `signal_workflow`, `manage_workflow`, `schedule_workflow`, `manage_schedule` | Durable deterministic and hybrid workflows | Mutations ask |
| Conductor | `conductor_list`, `conductor_get`, `conductor_register`, `conductor_start`, `conductor_status`, `conductor_signal`, `conductor_retry`, `conductor_schedule` | First-class Conductor operations through typed adapter | Policy-checked side effects |
| Human control | `ask_user`, `request_approval`, `record_decision`, `handoff_task` | Clarification, approvals, human review | Allow with rate limits |
| Agents | `spawn_agent`, `list_agents`, `message_agent`, `cancel_agent`, `merge_agent_result` | Parallel work and specialization | Ask for write-capable agents |
| Memory and context | `memory_read`, `memory_write`, `summarize_context`, `retrieve_context`, `pin_context`, `forget_context` | Continuity without leaking data | Writes ask or policy-dependent |
| Policy and audit | `get_policy`, `explain_permission`, `audit_lookup`, `export_audit_bundle` | Explainability and operations | Reads scoped; exports ask |
| Secrets | `secret_handle_request`, `credential_status`, `revoke_credential` | Credential lifecycle without model-visible raw secrets | Raw reveal denied |
| Telemetry and cost | `usage_summary`, `cost_estimate`, `quota_status`, `rate_limit_status` | Budget and operational feedback | Allow scoped reads |

Minimum day-one bundle:

- Read/search resources.
- Artifact creation.
- File patching with conflict checks.
- Python sandbox.
- HTTP fetch with domain policy.
- Process runner with allowlisted read-only commands.
- Git, package-manager, build, test, and code-index tools.
- Cloud identity, cost, billing, inventory, and recommendations for AWS, GCP, and Azure.
- Kubernetes, container, IaC, observability, and security read-only tools.
- MCP/app connector discovery and policy-proxied calls.
- Conductor workflow start/status/signal.
- Cron schedule create/pause/resume/delete.
- Human approval.
- Audit export.
- Kill switch controls.

Out of the box does not mean every tool can run everywhere. It means the harness ships with typed adapters, CLI profiles, parsers, policies, and tests for common operational domains. Availability still depends on installed CLIs, credentials, tenant policy, and runtime sandbox.

### CLI Pack Model

Raw shell is necessary for power users and unknown tasks, but production harnesses should prefer structured CLI wrappers for common work. A CLI wrapper constrains command construction, captures identity, parses structured output, and classifies side effects before execution.

```ts
type CliToolPack = {
  name: string;
  binaries: string[];
  versionCommands: string[][];
  identityCommands?: string[][];
  readOnlyCommands: CliCommandSpec[];
  mutatingCommands: CliCommandSpec[];
  defaultOutputFormat: "json" | "text";
  redactPatterns: string[];
  sideEffectClassifier: "static" | "parser" | "policy";
};

type CliCommandSpec = {
  command: string;
  allowedArgs: string[];
  requiredArgs?: string[];
  deniedArgs?: string[];
  requiresProfile?: boolean;
  requiresAccountGuard?: boolean;
  supportsDryRun?: boolean;
  outputParser: string;
};
```

CLI execution rules:

- Prefer `--json`, `-o json`, or equivalent structured output when available.
- Run identity commands before cloud, cluster, registry, or production operations.
- Bind execution to an explicit account, project, subscription, cluster, namespace, workspace, or profile when relevant.
- Reject commands that use `eval`, shell interpolation, opaque scripts, unbounded globbing, hidden pipes, or secret-printing flags unless explicitly approved.
- Cap output and preserve full output as an artifact when needed.
- Redact tokens, keys, connection strings, cookies, and authorization headers before model-visible output.
- Classify every CLI command as read, write, destructive, credential, network, cost-bearing, or unknown.
- Treat unknown commands as raw `run_process`, not as a safe CLI wrapper.
- For mutating CLIs, require dry-run or plan artifacts when the CLI supports them.

Default CLI packs should include wrappers for:

| Domain | Binaries | Read-Only Examples | Mutating Examples |
|---|---|---|---|
| Core shell utilities | `rg`, `fd`, `find`, `ls`, `stat`, `file`, `jq`, `yq`, `sed`, `awk`, `curl`, `openssl` | Search, inspect metadata, parse JSON/YAML, fetch allowlisted URLs | File writes, network posts, certificate generation |
| Git and GitHub | `git`, `gh` | `status`, `diff`, `log`, `show`, `blame`, PR/issue reads | commit, branch creation, push, PR create, merge, comment |
| JavaScript | `node`, `npm`, `pnpm`, `yarn` | version, list, audit, test, build | install, update, publish |
| Python | `python`, `uv`, `pip`, `poetry`, `pytest`, `ruff`, `mypy` | test, lint, typecheck, package info | install, lock update, publish |
| Go/Rust/Java/.NET | `go`, `cargo`, `mvn`, `gradle`, `dotnet` | test, build, dependency graph, audit | dependency update, publish |
| Containers | `docker`, `podman`, `docker compose`, `trivy`, `syft`, `grype` | inspect, logs, scan, SBOM | build, run, push, stop, remove |
| Kubernetes | `kubectl`, `helm`, `kustomize` | get, describe, logs, top, diff, template | apply, delete, rollout restart, scale, exec |
| IaC | `terraform`, `tofu`, `terragrunt`, `infracost`, `tflint`, `checkov` | fmt check, validate, plan, show, cost estimate, scan | apply, destroy, state mv/rm/import |
| Cloud | `aws`, `gcloud`, `az` | identity, billing, inventory, logs, metrics, recommendations | create/update/delete resources, IAM mutation |
| Databases | `psql`, `mysql`, `sqlite3`, `duckdb`, `bq`, `snowflake`, `databricks` | read-only queries, explain, export samples | DDL, DML, grants, large exports |
| Observability | `datadog-ci`, `newrelic`, `grafana`, `promtool`, `otelcol` tooling | query dashboards, alerts, rules, metrics | mute alerts, change rules, deploy collectors |
| Security | `semgrep`, `osv-scanner`, `npm audit`, `pip-audit`, `govulncheck`, `cargo audit` | local scans and reports | auto-fix, policy updates, external upload |

### Cloud Provider Tool Packs

Cloud support should be bundled as typed provider packs, not left to arbitrary CLI improvisation. The harness should support read-only FinOps and operations from day one, with mutation paths gated behind plan, approval, and account guards.

| Provider | Required Identity Guard | Cost And Billing Tools | Inventory And Utilization Tools | Notes |
|---|---|---|---|---|
| AWS | `aws sts get-caller-identity`, configured region/profile | Cost Explorer, Budgets, Cost and Usage Reports, Pricing API, Organizations account metadata | Resource Explorer, Config, CloudWatch metrics/logs, Compute Optimizer, Trusted Advisor where available, EC2/RDS/EKS/ECS/Lambda/S3 describe APIs | Cost Explorer is often payer-account scoped; CUR may require Athena/S3 access |
| GCP | `gcloud auth list`, `gcloud config get project`, billing account verification | Cloud Billing API, Billing Catalog API, BigQuery billing export, budgets | Cloud Asset Inventory, Recommender, Monitoring, Logging, Compute/GKE/Cloud SQL describe APIs | Detailed cost analysis usually requires BigQuery billing export |
| Azure | `az account show`, tenant/subscription verification | Cost Management Query API, Consumption Usage, Budgets, Pricesheet/Retail Prices API | Azure Resource Graph, Advisor, Monitor, Log Analytics, AKS/VM/SQL/Storage describe APIs | Subscription and tenant scoping must be explicit |

Cloud provider pack rules:

- Start every session with `cloud_identity` and show the account/project/subscription in the audit artifact.
- Default to read-only IAM roles for cost, inventory, utilization, and recommendations.
- Require explicit billing scope, time range, granularity, currency, timezone, and group-by dimensions.
- Enforce query windows and row limits because billing APIs can be slow, expensive, or quota-limited.
- Treat cost, usage, tags, account names, project names, and resource names as confidential by default.
- Never resize, stop, delete, purchase commitments, change budgets, or mutate IAM as part of cost analysis without a separate remediation approval.
- Generate recommendations as artifacts first; execution is a separate workflow.
- Normalize provider data into a common cost schema before analysis.

Common cloud cost schema:

```ts
type CloudCostRecord = {
  provider: "aws" | "gcp" | "azure";
  billingScope: string;
  accountOrProject: string;
  service: string;
  region?: string;
  usageType?: string;
  resourceId?: string;
  tags: Record<string, string>;
  startTime: string;
  endTime: string;
  cost: number;
  amortizedCost?: number;
  currency: string;
  usageQuantity?: number;
  usageUnit?: string;
};
```

Cloud cost tools that should work out of the box:

| Tool | Purpose | Provider Implementations |
|---|---|---|
| `cloud_cost_query` | Actual cost by time, service, account/project, region, tag, SKU, or resource | AWS Cost Explorer/CUR, GCP Billing Export/API, Azure Cost Management |
| `cloud_cost_forecast` | Forecast end-of-month and trend | AWS Cost Explorer forecast, provider exports plus local model, Azure forecast where available |
| `cloud_budget_status` | Budget and alert state | AWS Budgets, GCP Budgets, Azure Budgets |
| `cloud_anomaly_detect` | Identify unusual spend deltas | AWS Cost Anomaly Detection where available plus local baseline, GCP/Azure export analysis |
| `cloud_asset_inventory` | Resource inventory joined to tags and ownership | AWS Resource Explorer/Config, GCP Asset Inventory, Azure Resource Graph |
| `cloud_tag_coverage` | Untagged or poorly attributed spend | Provider cost dimensions plus inventory |
| `cloud_idle_resources` | Likely waste from low utilization or unattached assets | CloudWatch/Compute Optimizer, GCP Recommender/Monitoring, Azure Advisor/Monitor |
| `cloud_rightsizing_recommendations` | VM, database, container, and storage optimization ideas | AWS Compute Optimizer/Trusted Advisor, GCP Recommender, Azure Advisor |
| `cloud_commitment_coverage` | Savings Plans, Reserved Instances, committed-use discount, reservation coverage | AWS Savings Plans/RI reports, GCP CUD data, Azure Reservations |
| `cloud_pricing_lookup` | Unit price lookup for scenario modeling | AWS Pricing API, GCP Catalog API, Azure Retail Prices API |
| `cloud_unit_cost_report` | Cost per customer, environment, feature, team, or workload | Provider cost data plus business mapping artifact |

### Cloud Cost Analysis Workflow

A production-ready cloud cost workflow should be deterministic until it needs interpretation.

1. Resolve principal, tenant, cloud provider, billing scope, and allowed accounts/projects/subscriptions.
2. Run `cloud_identity` and fail closed if the active profile does not match the requested scope.
3. Collect cost data for a bounded time range with explicit granularity and dimensions.
4. Collect budgets, forecasts, anomalies, inventory, tags, utilization, and provider recommendations.
5. Normalize records into `CloudCostRecord` and store raw provider outputs as redacted artifacts.
6. Run deterministic aggregations for top services, top accounts/projects, trend, forecast, tag coverage, idle resources, and commitment coverage.
7. Use the model only for explanation, prioritization, and natural-language report generation, not for arithmetic truth.
8. Generate remediation proposals with estimated savings, risk, confidence, owner, rollback, and required approval.
9. If the user asks to execute remediation, create a separate workflow with plan/dry-run first.
10. Schedule recurring cost reviews through `schedule_workflow` with overlap protection and budget thresholds.

Example cost-analysis output artifacts:

- Executive summary.
- Service, account/project, region, tag, and workload breakdowns.
- Month-over-month and week-over-week deltas.
- Forecast against budget.
- Untagged spend report.
- Idle and rightsizing candidate list.
- Commitment coverage and utilization report.
- Remediation plan with approval requirements.
- Reproducibility bundle with queries, profile identity, policy version, and raw redacted data references.

### Coding Agent Tool Pack

For a coding agent, the harness should ship with more than file read/write and shell. It needs tools that preserve correctness under dirty workspaces, large repos, generated files, and CI failures.

| Tool Group | Day-One Tools | Key Guarantees |
|---|---|---|
| Workspace inspection | `repo_summary`, `git_status`, `git_diff`, `git_log`, `git_show`, `git_blame`, `list_files`, `search_files` | Never overwrite unknown user changes; keep snapshot IDs |
| Code navigation | `symbols`, `definition`, `references`, `call_graph`, `dependency_graph`, `semantic_code_search` | Prefer indexed facts over guessing |
| Editing | `apply_patch`, `safe_replace`, `format_file`, `write_artifact`, `notebook_edit` | Conflict detection, before/after diff, secret scan |
| Validation | `run_tests`, `run_targeted_tests`, `lint`, `typecheck`, `build`, `test_impact` | Capture command, env, exit code, output artifact |
| Dependency work | `dependency_tree`, `package_audit`, `lockfile_update`, `license_check` | Separate inspect from install/update |
| CI and PRs | `ci_status`, `ci_log_fetch`, `open_pr_draft`, `comment_pr`, `review_threads` | User-scoped auth, no publish without approval |
| Runtime diagnosis | `process_list`, `port_list`, `service_health`, `logs_tail`, `http_healthcheck` | Read-only by default |
| Release support | `changelog_draft`, `version_check`, `release_dry_run` | Publish is a separate high-risk action |

Coding-agent shell rule:

> The harness may expose raw shell, but coding agents should first use typed tools for file edits, git inspection, tests, package operations, and PR work. Raw shell is for gaps, and its output should become artifacts when it matters.

### Observability, Security, And Operations Packs

The day-one harness should also be useful for real SRE, security, and platform work.

| Pack | Tools | Production Default |
|---|---|---|
| Observability | CloudWatch, GCP Monitoring/Logging, Azure Monitor/Log Analytics, Datadog, New Relic, Prometheus, Grafana, Loki, OpenTelemetry query adapters | Read-only, redacted, time-bounded queries |
| Incident response | `incident_status`, `page_oncall`, `runbook_search`, `timeline_build`, `postmortem_draft` | Draft and read-only until explicit escalation |
| Kubernetes | `kubectl_get`, `kubectl_describe`, `kubectl_logs`, `kubectl_top`, `helm_template`, `kubectl_diff` | No `exec`, `delete`, `apply`, `scale`, or `rollout restart` without approval |
| IaC | Terraform/OpenTofu validate, plan, show, drift detection, Infracost, static checks | Plan artifacts before apply; state changes require approval |
| Security | Secret scan, SBOM, dependency audit, container scan, SAST, IAM analysis, cloud posture read | Local/read-only by default; containment requires approval |
| Databases and warehouses | Postgres, MySQL, SQLite, DuckDB, BigQuery, Snowflake, Redshift, Athena, Databricks | Read-only roles, row limits, explain/cost checks |

### Python Runtime For Analysis And Self-Evolution

The harness should include a Python runtime because many production tasks need data shaping, validation, one-off analysis, test generation, and adapter prototyping. This is not arbitrary code execution. It is a policy-controlled sandbox.

Allowed uses:

- Parse, transform, validate, and summarize data.
- Generate reports, charts, and artifacts.
- Write migration or adapter prototypes in a sandbox.
- Generate and run tests against proposed harness changes.
- Create workflow definitions, JSON schemas, fixtures, and replay cases.
- Propose self-evolution patches to skills, tools, policies, or workflows.

Forbidden by default:

- Direct access to raw secrets.
- Unapproved network access.
- Unapproved package installation.
- Writes outside the session workspace or artifact store.
- Modifying harness production code without review.
- Running generated code in the control plane.

Pre-bundled Python libraries should be pinned, scanned, and available offline:

| Category | Libraries |
|---|---|
| Core validation | `pydantic`, `jsonschema`, `attrs` |
| Data frames and arrays | `pandas`, `numpy`, `pyarrow`, `polars` |
| Local analytics | `duckdb`, `sqlite3` from standard library |
| Files and documents | `openpyxl`, `python-docx`, `pypdf`, `markdown`, `beautifulsoup4`, `lxml` |
| HTTP clients | `httpx`, `requests` |
| Config and serialization | `pyyaml`, `toml`, `orjson` |
| Dates and schedules | `python-dateutil`, `croniter`, `pytz` or `zoneinfo` |
| Templates | `jinja2` |
| Graphs and planning | `networkx` |
| Testing | `pytest`, `hypothesis` |
| Code quality | `ruff`, `black`, `mypy` |
| Visualization | `matplotlib`, `plotly` |
| Security helpers | `cryptography` for verification primitives, not custom crypto protocols |

Python runtime rules:

- Run in an ephemeral container or microVM with CPU, memory, wall-time, file, and output limits.
- Mount only approved input artifacts and an isolated output directory.
- Disable network by default; allow domain-scoped network only through policy.
- Use pinned package lockfiles and vulnerability scans.
- Persist code, inputs, outputs, package set, and execution metadata as artifacts.
- Treat generated files as proposals until approved and applied by normal file tools.
- Require tests for self-evolution patches before they can be proposed for merge.
- Route all filesystem writes through artifact output or policy-checked file tools.
- Never let Python mutate policy, secrets, schedules, workflows, or plugins directly.

Self-evolution rule:

> The harness may generate improvements to itself, but it may not silently apply them to trusted runtime surfaces. Self-evolution produces reviewed artifacts: patches, tests, workflow definitions, skills, policies, or adapter prototypes. Normal permission, testing, and rollout gates decide whether they become active.

## 15. Parallel Tool Execution

Parallelism is a performance optimization, not a semantic guarantee.

Rules:

- Read-only, idempotent, concurrency-safe tools may run concurrently.
- Side-effecting tools run serially unless explicitly declared safe and scoped.
- Shell or process tools run concurrently only when proven read-only and concurrency-safe.
- Tools that mutate shared context run serially or queue deterministic context updates.
- Results are emitted to the model in stable tool-call order.
- A failed read should not cancel unrelated reads.
- A failed operation in an explicitly dependent batch should cancel siblings.

Each tool should declare:

```ts
type ConcurrencyPolicy = {
  safeToRunInParallel: boolean;
  resourceLockMode: "none" | "read" | "write" | "exclusive";
  dependencyGroup?: string;
};
```

## 16. Background Tasks And Workflows

Long-running work should not block the conversation indefinitely.

### Background Task Flow

```text
tool starts long-running work
  -> register task atomically
  -> return initial tool result with task ID and output artifact
  -> stream progress as runtime events
  -> on completion, update task lifecycle first
  -> mark notified atomically
  -> emit one model-visible task notification
```

Task completion notifications should include:

- Task ID
- Status
- Summary
- Output artifact reference
- Error details if failed
- Resource changes
- Follow-up actions available

### Workflow Engine

Use a workflow engine when work is:

- Longer than a single session
- Event-driven
- Human-in-the-loop
- Retried across process restarts
- Coordinated across external systems
- Audited or SLA-bound

Workflow primitives:

- Start execution
- Wait for event or human signal
- Retry task
- Pause and resume
- Terminate
- Correlate by business key
- Query status
- Emit task notification into session
- Schedule recurring executions
- Pause, resume, update, and delete schedules

### Workflow Scheduling

Scheduling is a first-class workflow capability. A schedule is not just a delayed tool call; it is a durable intent to start a workflow later or repeatedly.

```ts
type WorkflowSchedule = {
  id: string;
  workflowName: string;
  workflowVersion?: number;
  cron: string;
  timezone: string;
  inputTemplate: Record<string, unknown>;
  correlationIdTemplate?: string;
  enabled: boolean;
  startAt?: string;
  endAt?: string;
  misfirePolicy: "skip" | "run_once" | "catch_up";
  overlapPolicy: "allow" | "skip_if_running" | "queue" | "cancel_previous";
  maxCatchUpRuns?: number;
  owner: string;
};
```

Schedule rules:

- Validate cron syntax before creating or updating a schedule.
- Require an explicit timezone; never rely on server local time silently.
- Pin the workflow version or define an explicit use-latest policy.
- Define daylight-saving-time behavior through `misfirePolicy`.
- Define overlap behavior so slow runs do not create uncontrolled concurrency.
- Use a deterministic correlation ID or idempotency key per scheduled fire.
- Store schedule definitions as artifacts with redacted input templates.
- Treat schedule create, update, pause, resume, and delete as side effects.
- Treat schedule read/list as scoped read operations.
- Re-run workflow policy analysis when a schedule's workflow definition, input template, or policy changes.
- When using Conductor or Orkes schedule support, map this schedule model to backend schedule APIs. If the backend lacks native schedules, use an external scheduler that starts workflows through the same `start_workflow` path.

### Conductor Skill Integration

Conductor should be treated as a first-class skill-backed durable workflow adapter. It can execute deterministic workflow skeletons and hybrid workflows, but durable orchestration is not the same thing as deterministic computation.

The harness loads the `conductor` skill through `SkillManager` and exposes a structured workflow tool surface backed by the Conductor CLI when available, with the bundled REST API script as fallback. The model should not operate the CLI directly as arbitrary shell. It should request typed workflow operations, and the harness adapter should perform the CLI or API call under policy.

Conductor-backed capabilities:

- List workflow definitions.
- Get workflow definition by name and version.
- Create or update workflow definitions from JSON artifacts.
- Start workflows asynchronously or synchronously.
- Start with version and correlation ID.
- Create, update, delete, pause, resume, and list schedules when the backend supports schedules.
- Get execution status, including task details.
- Search executions by status, name, and time range.
- Pause and resume executions.
- Terminate executions with a reason.
- Restart, retry, rerun, skip, or jump execution.
- Signal `WAIT` or `HUMAN` tasks.
- Poll and update task executions.
- Check task queue size.
- Start, inspect, and stop a local development server when allowed.

Conductor operational rules:

- Require `CONDUCTOR_SERVER_URL` or a named Conductor CLI profile before execution.
- Prefer `conductor` CLI commands when installed.
- Fall back to the skill's `conductor_api.py` only when the CLI is unavailable.
- Use structured `--json` output when available.
- Write workflow definitions and larger inputs to files first, then pass file paths to the CLI.
- Do not use `python3 -c` or shell post-processing to construct, validate, or parse workflow JSON.
- Never echo auth tokens, keys, secrets, or bearer values.
- Run workflow policy analysis before registration and before scheduled or manual starts.
- Reject workflow definitions and start inputs that contain raw secret-looking values; require secret handles or backend secret references.
- Store workflow definition JSON, start input JSON, schedule definitions, execution IDs, correlation IDs, and summaries as redacted artifacts.
- Treat workflow registration, start, schedule mutation, signal, retry, skip, jump, terminate, and local server lifecycle as side effects requiring permission.
- Route local Conductor server lifecycle through process and network sandbox policy, including port allocation, cleanup, and permission prompts.
- Ensure side-effecting Conductor tasks either execute through harness-controlled workers/proxies or run in a Conductor environment that enforces equivalent resource, permission, sandbox, secret, and audit policy.

### Deterministic Versus Agentic Routing

The harness should choose the execution mode from the nature of the work, not from model preference.

Use a deterministic workflow skeleton executed by Conductor when:

- The steps are known before execution.
- Control flow and decision rules are explicit, bounded, and machine-checkable.
- The same process will run repeatedly.
- The work needs retries, timeouts, SLAs, or audit history.
- The process waits on humans, events, or external systems.
- The process must survive harness restarts.
- Multiple systems must be coordinated with clear state transitions.
- Failures should be inspectable and retryable at task granularity.
- Runtime observations do not require open-ended judgment except at explicit `WAIT`, `HUMAN`, or agentic leaf tasks.

Use direct agentic execution when:

- The task is exploratory.
- The needed steps are unknown upfront.
- The model must inspect results and decide the next action dynamically.
- The work is one-off and low-risk.
- Human conversation is the main control loop.

Use a hybrid when:

- A deterministic workflow skeleton can own the reliable sequence, while agentic tasks handle judgment, transformation, summarization, routing, or exception handling.
- The agent should design or update the workflow, then Conductor should execute it.
- Conductor should run repeatable tasks and pause at `WAIT` or `HUMAN` tasks for agent or user decisions.
- Conductor should invoke side-effecting MCP, API, worker, or system actions only through harness-controlled workers/proxies, or through an environment with equivalent policy enforcement.

### Workflow Compilation Flow

```text
model proposes process
  -> harness classifies deterministic, agentic, or hybrid
  -> if deterministic or hybrid, compile process into workflow IR
  -> validate workflow IR against policy and available adapters
  -> analyze every workflow task for resource, capability, secret, retry, and side-effect policy
  -> render Conductor workflow JSON artifact
  -> ask permission to register or update definition
  -> register workflow through Conductor adapter
  -> ask permission to start execution with explicit input and correlation ID
  -> start workflow
  -> register execution as harness task
  -> monitor execution
  -> surface completion, failure, WAIT, HUMAN, or retryable state as task notification
```

The workflow IR should be provider-neutral. Conductor JSON is a backend rendering, not the harness's only internal workflow representation.

```ts
type WorkflowIR = {
  name: string;
  version?: number;
  description?: string;
  inputs: WorkflowInputSpec[];
  steps: WorkflowStep[];
  outputs?: Record<string, WorkflowExpression>;
  retryPolicy?: RetryPolicy;
  timeoutPolicy?: TimeoutPolicy;
  schedules?: WorkflowSchedule[];
  owner?: string;
};
```

Conductor rendering maps this IR to Conductor task types such as HTTP, SIMPLE, SWITCH, FORK_JOIN, JOIN, WAIT, HUMAN, SUB_WORKFLOW, START_WORKFLOW, EVENT, JSON_JQ_TRANSFORM, INLINE, and supported AI or MCP task types.

AI, MCP, and agent-backed steps are non-deterministic leaves unless their inputs, model or tool version, policy, and outputs are pinned or replayed. Classify these as durable orchestrated steps, not deterministic computation.

### Workflow IR Step Model

Workflow IR should make policy analysis possible before rendering to Conductor.

```ts
type WorkflowStep =
  | HttpStep
  | ToolProxyStep
  | AgentStep
  | HumanStep
  | WaitStep
  | SwitchStep
  | ParallelStep
  | SubWorkflowStep
  | TransformStep
  | EventStep
  | TerminateStep;

type BaseStep = {
  id: string;
  refName: string;
  displayName?: string;
  input: Record<string, WorkflowExpression>;
  output?: Record<string, WorkflowExpression>;
  retry?: RetryPolicy;
  timeout?: TimeoutPolicy;
  sideEffects: SideEffectPlan[];
  requiredCapabilities: Capability[];
  resources: ResourceRef[];
  dataClassification?: "public" | "internal" | "confidential" | "restricted" | "regulated";
};

type ToolProxyStep = BaseStep & {
  kind: "tool_proxy";
  toolName: string;
  deterministic: boolean;
};

type AgentStep = BaseStep & {
  kind: "agent_task";
  agentType: string;
  allowedTools: string[];
  permissionMode: "read_only" | "default" | "dont_ask" | "trusted";
  contextScope: "none" | "workflow_input" | "selected_artifacts" | "policy_summary";
};

type HumanStep = BaseStep & {
  kind: "human";
  approval: ApprovalRequirement;
};

type SwitchStep = BaseStep & {
  kind: "switch";
  expression: WorkflowExpression;
  cases: Record<string, WorkflowStep[]>;
  defaultCase?: WorkflowStep[];
};

type ParallelStep = BaseStep & {
  kind: "parallel";
  branches: WorkflowStep[][];
  joinPolicy: "all" | "any" | "quorum";
};
```

IR validation rules:

- `refName` must be unique across the rendered workflow.
- Every step must declare resources and required capabilities.
- Every side-effecting step must declare an idempotency or compensation strategy.
- Every agent, MCP, LLM, browser, email, payment, cloud, and database mutation step is non-deterministic or side-effecting unless proven otherwise.
- Every branch must have bounded termination or an explicit timeout.
- Every schedule must reference a version-pinned workflow or an explicit use-latest policy.

### Conductor Rendering Rules

| IR Step | Conductor Rendering | Policy Requirement |
|---|---|---|
| `tool_proxy` HTTP/API | `HTTP` only when routed to harness policy proxy; otherwise `SIMPLE` worker | Domain, credential, and side-effect policy |
| `agent_task` | `SIMPLE` worker or callback task owned by harness | Agent bridge contract and idempotency key |
| `human` | `HUMAN` or `WAIT` plus signal tool | Approval policy and expiry |
| `wait` | `WAIT` | Time bounds or signal contract |
| `switch` | `SWITCH` | Machine-checkable expression |
| `parallel` | `FORK_JOIN` plus `JOIN` or `EXCLUSIVE_JOIN` | Resource-lock and concurrency policy |
| `sub_workflow` | `SUB_WORKFLOW` | Child workflow version and policy analysis |
| `start_workflow` | `START_WORKFLOW` | Correlation and idempotency policy |
| `transform` | `JSON_JQ_TRANSFORM` or `INLINE` | Bounded CPU/output and no secret leakage |
| `event` | `EVENT` or policy-proxied publish worker | Event sink authorization |

The compiler should reject a workflow that cannot be statically analyzed into resource and capability descriptors.

### Hybrid Workflow Patterns

| Pattern | Shape | Use Case |
|---|---|---|
| Agent designs, Conductor executes | Agent compiles workflow JSON, registers it, starts execution, then monitors | Repeatable process created from a user request |
| Conductor skeleton, agent task | Workflow reaches an `agent_task` implemented by a harness-controlled worker or callback adapter | Judgment, extraction, classification, exception handling |
| Conductor waits, agent decides | Workflow pauses at `WAIT` or `HUMAN`; harness or user signals result | Approval, review, policy decision |
| Agent supervises workflow | Agent monitors status, diagnoses failed task, proposes retry or fix | Operational recovery |
| Workflow invokes tools through policy proxy | Conductor calls harness-controlled HTTP, MCP, event, or worker adapters | Stable integrations with retries, audit, and consistent policy |
| Cron schedule starts workflow | Schedule fires and starts a workflow with redacted input template and correlation ID | Recurring jobs, reporting, sync, maintenance |

### Agent Task Bridge Contract

A workflow may invoke an agent only through a defined bridge, not by ad hoc process launch.

An `agent_task` bridge must define:

- Conductor task type and task reference name.
- Harness agent type, allowed tools, permission mode, and context scope.
- Idempotency key derived from workflow ID, task ID, retry count, and task reference.
- Input and output schemas.
- Transcript and artifact retention policy.
- Heartbeat, response timeout, and cancellation behavior.
- Retry behavior and whether retries reuse or fork transcript state.
- Exactly-one completion update back to Conductor.
- Secret-handle policy; raw secrets are forbidden in task input and output.
- Failure mapping to `FAILED` or `FAILED_WITH_TERMINAL_ERROR`.

### Conductor Execution State Mapping

| Conductor State | Harness Mapping |
|---|---|
| `RUNNING` | Background `workflow` task with `lifecycle: running` |
| `COMPLETED` | `lifecycle: completed`; emit one terminal notification |
| `FAILED` | `lifecycle: failed`; include failed task, error, retry count, and retry options |
| `TIMED_OUT` | `lifecycle: failed`; classify as timeout and expose retry or rerun options |
| `TERMINATED` | `lifecycle: cancelled` or `killed` depending initiator |
| `PAUSED` | `lifecycle: running` with `externalStatus: paused` |
| `WAIT` or `HUMAN` task in progress | `lifecycle: running` with required signal or approval action |

Before registering or starting a workflow with worker-backed tasks, the harness should verify required task definitions and worker availability where possible. Missing SIMPLE or DYNAMIC workers should block start unless the user explicitly confirms a likely-stalling execution.

## 17. Subagents And Delegation

A subagent is a child conversation engine with scoped context, scoped tools, scoped policy, and a separate transcript.

Use subagents for:

- Parallel independent research
- Long-running background investigations
- Domain-specialized execution
- Isolated risky work
- Independent implementation slices
- Monitoring a task while the parent continues

Subagent rules:

- Each child has a stable ID.
- Each child has its own transcript and task state.
- Each child has its own abort controller.
- Parent permissions do not automatically leak into children.
- Child tools are built from child effective policy.
- Child agents that cannot prompt must deny unresolved asks or bubble them according to config.
- Background children report through task state, not ad hoc chat.
- Child cleanup clears scoped tools, hooks, tool servers, memory overlays, and child processes.
- Parent context fork must not include unresolved tool calls.

### Isolation Modes

| Mode | Use When | Trade-off |
|---|---|---|
| `same_session_readonly` | Child only reads or analyzes | Fast, low isolation |
| `workspace_snapshot` | Child needs a stable view | More storage, safer reads |
| `worktree_or_branch` | Child edits versioned files | Good merge story, coding-specific |
| `container` | Child runs commands or dependencies | Stronger process isolation |
| `remote_sandbox` | High-risk or expensive work | Operational overhead |
| `external_workflow` | Durable business process | Higher latency, better audit |

If a child inherits references to mutable parent resources, the harness must either snapshot them, translate paths or IDs, or explicitly tell the child that it is operating on a clean base.

## 18. Context, Memory, And Retrieval

The harness must decide what the model sees.

### Context Sources

- Current user input
- Durable transcript tail
- Compact summaries
- Relevant memory
- Resource summaries
- Tool schemas
- Policy summary
- Task state
- Artifact previews
- Retrieved documents
- Pending approvals

### Context Rules

- Prefer exact recent transcript over summaries.
- Keep provider-bound messages byte-stable when needed for cache or signature validity.
- Replace large content with artifact references and bounded previews.
- Do not include raw secrets.
- Do not include regulated or cross-tenant data unless the active principal, policy, and purpose allow it.
- Include enough policy context for the model to avoid futile actions.
- Track why each context item was included.
- Compact before the context window is full, not after a provider error.

### Context Packages

Context should be assembled as typed packages so the harness can explain, replay, trim, and audit what the model saw.

```ts
type ContextPackage = {
  id: string;
  kind: "transcript" | "policy" | "resource" | "artifact" | "memory" | "task" | "workflow" | "tool_schema" | "approval";
  priority: number;
  tokenEstimate: number;
  sourceRefs: string[];
  sensitivity: "public" | "internal" | "confidential" | "restricted" | "regulated";
  content: unknown;
  summary?: string;
  expiresAt?: number;
};
```

Context assembly order:

1. Required protocol messages and unresolved tool-result obligations.
2. Current user request and directly referenced resources.
3. Active policy summary and permission mode.
4. Active task, workflow, schedule, and approval state.
5. Relevant artifact previews and retrieved resources.
6. Relevant memory, scoped by tenant, principal, and purpose.
7. Tool schemas, deferred when possible.

Context rules:

- Never trim unresolved tool-use/result obligations.
- Prefer artifact references over full content for large outputs.
- Include provenance with summaries.
- Expire sensitive context aggressively.
- Record context package IDs in the model request audit event.

### Memory Types

| Memory | Scope | Examples |
|---|---|---|
| Session memory | One conversation | User's current goal, active resources |
| Project memory | Shared work area | Preferred commands, schemas, domain terms |
| User memory | Across sessions | User preferences, recurring constraints |
| Organization memory | Managed | Policies, approved integrations |
| Tool memory | Adapter-specific | API pagination cursors, sync checkpoints |

Memory writes should be explicit, inspectable, and reversible.

## 19. Persistence And Recovery

Persistence is a correctness layer, not just logging.

Persist:

- Durable messages
- Tool calls and results
- Permission decisions
- Resource snapshots or version IDs
- Task state
- Artifact metadata
- Hook decisions
- Plugin versions
- Budget usage
- Model provider request metadata
- Recovery tombstones and compaction records

Rules:

- Use append-only event logs for normal writes.
- Store large outputs separately.
- Use atomic file or database transactions for state changes.
- For file-backed stores, write temp file, flush, rename, and fsync parent directory where supported.
- On crash, recover the longest valid prefix and append compensating records.
- Never rewrite large transcripts just to remove orphaned events; append tombstones.
- Migrate old record shapes during resume.

## 20. Hooks And Plugins

Hooks let trusted code observe or modify lifecycle behavior.

Hook events:

| Event | Purpose |
|---|---|
| `session_start` | Add managed context or policy |
| `user_input` | Validate or enrich user input |
| `pre_model_call` | Adjust context or provider options |
| `post_model_call` | Inspect model output |
| `pre_tool_use` | Validate, block, or modify tool input |
| `permission_request` | Provide policy decision advice |
| `post_tool_use` | Inspect output, classify, or trigger follow-up |
| `task_complete` | Process background completion |
| `session_end` | Cleanup and audit |
| `subagent_start` | Add scoped child context |
| `subagent_stop` | Validate child output |

Hook rules:

- Hook output must be structured and schema-validated.
- Unstructured stdout is audit text, not authorization.
- Hooks have timeouts and output caps.
- Hook failures fail closed only when configured.
- Hook-mutated tool input must be revalidated.
- Permission hook results remain provisional until final mode policy is applied.
- Async hooks are background tasks with cleanup and bounded output.
- User-controlled hooks are disabled in managed or high-security policy.

Plugin rules:

- Validate manifests.
- Namespace every contribution.
- Pin plugin versions by immutable version, commit, digest, or signature.
- Enforce marketplace and source policy.
- Prune tools and hooks immediately when a plugin is disabled.
- Store plugin secrets in secure storage, not general settings.
- Never let plugin install or update occur as an ordinary model side effect.

## 21. Secrets And Credentials

Secrets are not context.

Rules:

- The model receives secret handles, capability labels, or success flags, not raw values.
- Tools request credentials from `SecretBroker` at execution time.
- Credential scope is bound to resource, tool, task, and policy.
- Secret values are redacted from logs, transcripts, telemetry, artifacts, and error messages.
- Explicit user reveal, if supported, is UI-only, non-durable, strongly confirmed, and never model-visible.
- Secret scans run before transcript write, artifact preview, telemetry export, and UI display.

## 22. Data Governance

Production agents often touch sensitive data before they touch dangerous tools. Treat data movement as a side effect.

Data governance rules:

- Classify inputs, retrieved context, tool outputs, artifacts, memory writes, and telemetry before persistence or display.
- Enforce tenant, region, and data-residency restrictions at resource resolution time.
- Block regulated data from model providers or tools that are not approved for that data class.
- Apply purpose limitation: data retrieved for support should not silently become sales outreach context.
- Preserve source provenance for legal, medical, financial, security, and compliance outputs.
- Use redacted previews for artifacts containing PII, PHI, PCI, secrets, or customer confidential data.
- Support deletion, retention, legal hold, and audit export policies per tenant and data class.
- Treat external sharing, publishing, emailing, and data export as high-risk side effects.

## 23. Human-In-The-Loop Control

The harness should treat humans as first-class participants.

Human interaction types:

- Clarification
- Permission approval
- Business approval
- Credential authorization
- Manual task assignment
- Review and sign-off
- Emergency stop

Rules:

- Prompts must be specific and bounded.
- Prompts should show what will happen, what resources are touched, and whether the action is reversible.
- Permission prompts are not general chat messages.
- Headless runs must deny, defer, or route approvals to a configured external channel.
- Repeated prompts for the same action should be deduplicated.

## 24. High-Level Algorithms

### Bootstrap Algorithm

```text
load static config
load managed policy
load user and workspace settings
validate settings
initialize persistence
initialize secret broker
initialize resource adapters
load skills from trusted sources
validate skill manifests, command allowlists, paths, and integrity
load plugins from trusted sources
validate plugin manifests and integrity
initialize workflow backend adapters, including Conductor when configured
register tools
filter tools by policy
initialize model provider
initialize event bus
recover unfinished tasks
run session_start hooks
start conversation engine
```

If bootstrap safety checks fail, start in degraded safe mode with side-effecting tools disabled.

### User Input Algorithm

```text
receive input
classify as control command, normal prompt, file/resource attachment, or external event
validate attachment/resource access
run user_input hooks
if blocked:
  emit warning and stop
append durable user message when appropriate
start conversation turn
```

### Conversation Turn Algorithm

```text
while turn not complete:
  enforce budget and max turn count
  build provider-valid context
  compact if needed
  call model
  stream assistant events
  collect tool calls
  if no tool calls:
    run final checks
    return final response
  partition tool calls into safe batches
  execute each batch
  append one result per tool call
```

### Execution Mode Selection Algorithm

```text
receive user goal or model-proposed plan
identify whether steps are known, repeatable, and auditable
identify whether the plan needs event waits, human waits, retries, or restart survival
identify whether decisions depend on unknown future observations
identify whether control flow and decision rules are explicit, bounded, and machine-checkable
if the task is exploratory or underspecified:
  choose agentic execution
else if decisions depend on unknown future observations:
  choose hybrid workflow with deterministic skeleton and agentic decision points
else if steps are known, control flow is machine-checkable, and durable orchestration matters:
  choose deterministic workflow skeleton
else:
  choose hybrid workflow with deterministic skeleton and agentic decision points
record the selected mode and reason in the audit log
```

The model may suggest an execution mode, but the harness should make the final choice from structured criteria.

### Conductor Workflow Operation Algorithm

```text
receive typed workflow operation
verify Conductor skill and adapter are enabled
verify skill source, path, command allowlist, and integrity policy
verify CONDUCTOR_SERVER_URL or selected CLI profile
validate operation input
if operation creates or updates a definition:
  render workflow JSON artifact
  validate required fields and task reference uniqueness
  reject raw secret-looking values; require secret handles or backend secret references
  analyze workflow tasks into resource, capability, secret, retry, and side-effect descriptors
  reject unauthorized task types, endpoints, domains, workers, or secrets
  preflight SIMPLE and DYNAMIC worker-backed tasks
  ask permission to register or update based on downstream side effects
  call conductor workflow create or update with file path
if operation starts execution:
  render input JSON artifact when needed
  reject raw secret-looking values; require secret handles or backend secret references
  require workflow name, version policy, and correlation ID policy
  preflight worker-backed tasks if definition is available
  ask permission to start based on workflow definition, input, and downstream side effects
  call conductor workflow start
  store workflow ID and correlation ID
  register harness background workflow task
if operation creates or updates a schedule:
  validate cron expression, timezone, misfire policy, overlap policy, and input template
  reject raw secret-looking values; require secret handles or backend secret references
  analyze scheduled workflow definition and input template under current policy
  ask permission to create or update recurring side effect
  call backend schedule create or update when supported, or configure external scheduler through start_workflow path
if operation pauses, resumes, or deletes a schedule:
  ask permission unless policy already allows this exact schedule mutation
  call backend schedule pause, resume, or delete
if operation monitors execution:
  call conductor workflow get-execution or search
  summarize status, failed task, retry count, and blocked task
if operation signals or manages execution:
  ask permission unless policy already allows this exact action
  call conductor task signal, workflow retry, pause, resume, terminate, rerun, skip, or jump
if operation manages local Conductor server lifecycle:
  route through run_process-grade sandboxing, port policy, cleanup, and permission
return one model-visible tool result with structured summary
```

The adapter should prefer the `conductor` CLI. If unavailable, it may use the skill's REST API script. It must not construct JSON through ad hoc shell parsing, and it must never print credentials.

### Permission Decision Algorithm

```text
derive operation descriptor
check hard deny rules
check resource policy
check tool-specific safety
check sandbox enforceability
check explicit allow rules
run permission hooks
normalize provisional result
apply permission mode
if ask and mode is dont_ask:
  deny
if ask and prompt available:
  prompt user
if ask and prompt unavailable:
  deny
return final decision
```

### Tool Result Mapping Algorithm

```text
receive raw output or error
classify sensitivity
redact secrets and private data according to policy
if output exceeds model limit:
  store artifact and return preview
if binary or media:
  store artifact and return metadata
if error:
  return structured recoverable error
append audit record
return model-facing tool result
```

### Resume Algorithm

```text
load session metadata
load transcript prefix up to safe limit
load tasks and artifacts
validate message graph
repair provider-incompatible records
drop orphaned tool results
insert synthetic results for unresolved tool calls when needed
apply tombstones and compaction records
recover background task monitors
emit resume summary
continue from provider-valid state
```

### Interrupt Algorithm

```text
user or system sends interrupt
cancel model stream
for each running foreground tool:
  if interrupt behavior is cancel:
    abort tool
  if interrupt behavior is finish_atomically:
    wait or move to background
  if interrupt behavior is background:
    flip task executionMode to background
append synthetic results for cancelled tool calls
persist state
return control to user
```

## 25. Edge Cases And Corner Cases

### Model And Protocol

| Edge Case | Required Behavior |
|---|---|
| Model emits invalid JSON | Return validation error as tool result |
| Model emits unknown tool | Return unknown-tool error |
| Model emits duplicate tool IDs | Treat as protocol error; synthesize errors |
| Assistant tool use lacks result | Insert synthetic failure before next model call |
| Tool result lacks tool use | Drop or quarantine before provider call |
| Provider stream is interrupted | Tombstone partial message and recover valid history |
| Provider fallback after partial output | Discard abandoned tool IDs and retry cleanly |
| Provider-specific hidden fields | Preserve for same provider, strip for incompatible provider |

### Resources

| Edge Case | Required Behavior |
|---|---|
| Resource moved after read | Fail with conflict and require re-read |
| Resource changed before write | Fail with conflict unless operation is merge-safe |
| Resource is symlink or alias | Resolve real target before policy |
| Resource is binary | Return metadata or artifact, not raw bytes |
| Resource is huge | Stream, sample, or summarize with explicit limits |
| Resource permission denied | Return structured OS or provider error |
| Resource adapter unavailable | Degrade and explain unavailable capability |

### Tools

| Edge Case | Required Behavior |
|---|---|
| Tool hangs | Timeout and kill or background according to policy |
| Tool exceeds output cap | Stop or truncate safely; persist bounded artifact |
| Tool returns sensitive data | Redact before display, transcript, and telemetry |
| Tool partially succeeds | Return structured partial result and compensating options |
| Tool has non-idempotent retry | Require idempotency key or user approval |
| Hook modifies input | Revalidate modified input |
| Hook blocks repeatedly | Tell model to stop retrying that action |

### Permissions

| Edge Case | Required Behavior |
|---|---|
| Headless action asks | Deny, defer, or route externally; never hang |
| Allow and deny both match | Deny wins |
| Sandbox cannot enforce policy | Deny or ask for explicit unsafe escalation |
| Approval times out | Return denied or expired result |
| User approval arrives late | Re-check resource state before execution |
| Policy changes mid-task | Apply to future actions; running task follows configured cancellation policy |
| Principal delegation expired | Deny and require fresh authorization |
| Same user prepares and approves high-risk action | Reject if segregation-of-duties policy applies |
| Cross-tenant resource requested | Deny unless explicit managed policy allows it |

### Data Governance

| Edge Case | Required Behavior |
|---|---|
| Regulated data would be sent to unapproved model provider | Block or route to approved provider |
| Tool output mixes tenants | Quarantine output and return policy error |
| Artifact contains PII or secrets | Store full artifact under restricted policy and expose only redacted preview |
| Memory write contains customer confidential data | Require scoped memory and retention policy or reject |
| Data residency would be violated | Deny export or route to compliant region |

### Background Work

| Edge Case | Required Behavior |
|---|---|
| Task finishes while model is thinking | Queue one notification for next safe injection point |
| Task completes twice | Deduplicate by task ID and terminal transition |
| Parent exits | Continue or cancel according to ownership policy |
| Child agent spawns process | Kill owned processes during child cleanup |
| Output grows forever | Enforce artifact and output caps |
| Workflow signal duplicated | Use idempotency key or correlation ID |

### Durable Workflows And Conductor

| Edge Case | Required Behavior |
|---|---|
| Conductor CLI unavailable | Fall back to approved skill API script or report unavailable capability |
| `CONDUCTOR_SERVER_URL` or profile missing | Ask for configuration or deny workflow execution |
| Auth token required | Use secret broker or environment; never echo token |
| Workflow definition invalid | Return validation errors before registration |
| Task reference names duplicated | Reject workflow definition before registration |
| Side-effecting Conductor task bypasses harness | Reject unless it uses a harness-controlled worker/proxy or equivalent policy enforcement |
| AI, MCP, or agent step is called deterministic | Classify as non-deterministic leaf unless inputs, versions, policies, and outputs are pinned or replayed |
| Worker-backed task has no worker | Block start or require explicit user confirmation after warning |
| Workflow start is retried | Use correlation ID or idempotency policy to avoid duplicate business execution |
| Workflow is stuck at `WAIT` or `HUMAN` | Surface required signal as approval/task notification |
| Workflow fails after agent context changed | Diagnose from Conductor execution state, not stale transcript assumptions |
| Workflow definition updated during execution | Preserve execution version and show version in status |
| Schedule cron is invalid | Reject before creating or updating schedule |
| Schedule timezone missing | Reject; require explicit timezone |
| Scheduled run overlaps previous run | Apply `overlapPolicy` deterministically |
| Scheduled run missed during outage | Apply `misfirePolicy` and cap catch-up runs |
| Scheduled input contains raw secret | Reject; require secret handle or backend secret reference |

### Persistence

| Edge Case | Required Behavior |
|---|---|
| Disk full | Stop side effects and report persistence failure |
| Crash mid-write | Recover append-only prefix or atomic rename state |
| Corrupt transcript | Recover longest valid prefix |
| Tombstone rewrite too large | Append compensating tombstone record |
| Version upgrade | Migrate or tolerate old shapes |
| Artifact missing | Return missing-artifact error and preserve transcript validity |

## 26. Production Threat Model

The harness should assume adversarial prompts, compromised tools, stale policies, confused deputies, and partial infrastructure failure.

| Threat | Example | Defense |
|---|---|---|
| Prompt injection | Web page tells model to export secrets | Tool and data policy ignore model claims; secrets never enter context |
| Confused deputy | Agent uses user's broad token for a workflow-owned action | Principal delegation with scoped, expiring credentials |
| Cross-tenant leakage | Search tool returns another customer's records | Tenant-bound resource resolution and data-governance checks |
| Workflow policy bypass | Conductor HTTP task calls external API directly | Require harness policy proxy or equivalent enforced environment |
| Schedule abuse | User creates cron that repeatedly sends emails or drains quota | Schedule policy, quotas, overlap policy, and kill switch |
| Retry amplification | Failed downstream causes many agents/workflows to retry | Idempotency keys, retry budgets, and circuit breakers |
| Tool supply-chain compromise | Plugin or skill adds malicious hook | Integrity pinning, source policy, namespacing, unload controls |
| Secret exfiltration through artifacts | Tool writes token into report preview | Secret scanning before artifact preview, transcript, telemetry, and display |
| Stale approval | User approves action after resource changed | Re-check resource snapshot and policy at execution time |
| Non-deterministic replay drift | AI leaf produces different result on retry | Pin inputs/model/tool versions or store replayed outputs |
| Browser phishing | Agent submits credentials into lookalike site | Browser origin policy, form-submit approval, screenshot evidence |
| Data residency violation | Model provider in wrong region receives regulated content | Provider routing by data classification and tenant region |
| Physical-world hazard | Device command has unsafe actuator effect | Device safety adapter, bounded commands, emergency stop |

Threat-model rules:

- Every new adapter must declare its threat model before being exposed to the model.
- Every new production use case must identify its highest-impact irreversible action.
- Every external side effect must be testable in dry-run or simulation where possible.
- Incident learnings become policy tests, adversarial tests, or rollout gates.

## 27. Worked Production Flows

### Support Refund

Goal: resolve a customer ticket and issue a refund if policy allows.

Flow:

1. `PrincipalResolver` resolves the support agent and tenant.
2. Agent reads ticket, order, and payment metadata through scoped resource adapters.
3. Data governance classifies customer PII and payment metadata as restricted.
4. Agent proposes refund amount and reason.
5. `PermissionEngine` classifies refund as high or critical based on amount.
6. If under threshold, one approval may allow `mutate_data` or payment API refund through policy proxy.
7. If over threshold, multi-party approval and segregation of duties apply.
8. Refund tool uses idempotency key based on ticket ID and payment ID.
9. Result artifact stores redacted payment reference, refund ID, and customer-safe summary.

Failure checks:

- If approval arrives late, re-check payment and order state.
- If refund status is ambiguous, reconcile with payment provider before retry.
- If the customer asks for deletion, route to a separate privacy workflow.

### SRE Remediation

Goal: diagnose production latency and restart a service only if safe.

Flow:

1. Agent starts in `read_only` mode and reads telemetry, logs, deploy history, and runbooks.
2. It drafts a remediation plan with blast radius and rollback.
3. `PermissionEngine` marks restart/scale/deploy as high-risk production action.
4. Human approver with on-call scope approves, possibly with MFA.
5. Execution runs through cloud adapter with scoped service account and region/account constraints.
6. Workflow monitors health checks and either completes or triggers rollback/incident escalation.

Failure checks:

- If telemetry provider is degraded, do not infer success from missing data.
- If rollback fails, freeze further autonomous actions and page human.
- Break-glass mode requires reason, expiry, and post-incident review.

### Scheduled ETL Sync

Goal: sync CRM accounts to warehouse every hour.

Flow:

1. Agent drafts workflow IR with read CRM, transform, write warehouse, and reconciliation steps.
2. `WorkflowCompiler.analyze` verifies CRM read scope, warehouse write scope, PII classification, idempotency, and retry behavior.
3. Conductor workflow is registered with version pinning.
4. `WorkflowSchedule` is created with cron, timezone, `skip_if_running`, and `run_once` misfire policy.
5. Each scheduled fire uses a schedule principal and correlation ID template.
6. Workflow writes reconciliation artifact and emits metric counts.

Failure checks:

- Overlap skips if prior sync is still running.
- Catch-up is capped after outage.
- Raw credentials in workflow input are rejected.
- If warehouse schema drifts, workflow fails with actionable diagnostic instead of silently truncating.

### Coding PR Agent

Goal: fix a test failure and open a pull request.

Flow:

1. Agent reads repository and failing CI logs.
2. Editing child agent runs in isolated worktree or container.
3. File edits require exact old text or current snapshot.
4. Tests run through process sandbox with output artifact.
5. Patch artifact and summary are reviewed.
6. PR creation uses user-delegated GitHub principal and scoped token.

Failure checks:

- Dirty parent workspace is snapshotted or refused.
- Secrets in diff or logs are redacted and block PR creation.
- If tests are flaky, agent reports uncertainty instead of claiming success.

### Security Alert Triage

Goal: investigate a suspicious login and optionally disable a user session.

Flow:

1. Alert payload is treated as hostile input.
2. Agent enriches with identity, device, geolocation, and recent activity using read-only tools.
3. Agent classifies severity and proposes containment.
4. Session disable is high-risk account action requiring policy approval.
5. Containment action uses idempotency key and records chain-of-custody artifact.

Failure checks:

- Alert-provided URLs are opened only in isolated browser/sandbox.
- If identity data spans tenants, output is quarantined.
- If confidence is low, ask human rather than disable account.

### Cloud Cost Optimization

Goal: analyze AWS, GCP, or Azure spend and produce safe savings recommendations.

Flow:

1. User selects provider, billing scope, accounts/projects/subscriptions, time range, and grouping dimensions.
2. Agent runs provider-specific `cloud_identity` and verifies the active profile matches the requested scope.
3. Agent queries cost, forecast, budgets, anomalies, inventory, tags, utilization, pricing, and provider recommendations through typed cloud tools.
4. Deterministic analysis computes top spend drivers, deltas, forecast variance, untagged spend, idle resources, rightsizing candidates, and commitment coverage.
5. Model explains findings and ranks recommendations, but arithmetic comes from deterministic aggregations.
6. Report artifact stores redacted raw data references, normalized cost tables, charts, assumptions, confidence, and reproducibility metadata.
7. If the user wants recurring analysis, `schedule_workflow` creates a cron-based cost review with explicit timezone and overlap policy.
8. If the user wants remediation, the harness creates a separate plan workflow using provider/IaC dry-run tools before any mutation.

Failure checks:

- If payer account, billing account, subscription, or project identity does not match, fail closed.
- If billing export is incomplete or delayed, mark confidence low and do not infer savings from missing data.
- If tags are absent, separate "unallocated" spend rather than assigning it heuristically without evidence.
- If provider recommendation APIs disagree with utilization data, show both and require human review.
- If a remediation would stop, resize, delete, buy commitments, alter budgets, or mutate IAM, require separate approval and rollback plan.

## 28. What-If Scenarios

### What If The User Asks For Fully Autonomous Mode?

Require explicit scope, time budget, cost budget, resource allowlist, side-effect policy, and kill switch. Autonomous does not mean unsandboxed or unaudited.

### What If The Agent Needs A Tool It Does Not Have?

Let it request capability discovery. The harness may expose a tool search result, ask the user to install or enable a plugin, or deny because the capability is unavailable. Do not let the model install arbitrary executable plugins without approval and integrity checks.

### What If A Tool Needs Credentials?

The model receives a handle or capability name. The tool obtains scoped credentials from `SecretBroker` during execution. If authorization is missing, start an explicit auth flow or ask the user through a UI-only channel.

### What If A Side Effect Cannot Be Undone?

Raise the permission threshold. Show the irreversible nature in the prompt. Require idempotency keys where possible. Prefer dry-run or preview mode before execution.

### What If Multiple Agents Need The Same Resource?

Use resource locks, snapshots, or isolated branches. If true concurrent writes are necessary, require a merge protocol and conflict detection.

### What If The Agent Runs Out Of Context Mid-Task?

Pause tool planning, compact history, summarize active tasks and resources, preserve unresolved tool-result obligations, then continue. Do not drop required tool results.

### What If A Browser Action Is About To Submit A Form?

Treat submit as a side effect. Show target site, form fields, account identity, and expected outcome. Ask unless policy explicitly allows it.

### What If A Database Query Could Be Expensive?

Classify as read but budget-sensitive. Use explain, row limits, timeouts, and read replicas where possible. Ask or deny if it could lock tables or exceed cost.

### What If A Device Command Could Affect Physical State?

Use a device-specific safety adapter. Require explicit scope, emergency stop, bounded command set, and fail-safe behavior. Prefer simulation or dry-run first.

### What If A User Asks For A Repeatable Process?

Have the agent draft the process, then compile it to workflow IR and render a Conductor workflow definition. Ask before registering it. After registration, start it with explicit input, correlation ID, and monitoring policy. The agent should supervise the execution instead of manually repeating each step.

### What If A User Wants The Workflow To Run On A Cron?

Create a `WorkflowSchedule` with cron expression, explicit timezone, input template, correlation ID template, misfire policy, and overlap policy. Validate the scheduled workflow and input through the same policy analyzer used for manual starts. Ask before creating or updating the schedule. If Conductor or Orkes schedule APIs are available, map to them; otherwise use an external scheduler that calls the harness `start_workflow` path.

### What If The Process Is Mostly Deterministic But Needs Judgment?

Put stable steps in Conductor and isolate judgment into explicit agentic tasks, human tasks, or model-backed workers. This keeps retries, waits, and audit durable and predictable while preserving flexibility where the process genuinely needs interpretation.

### What If A Conductor Workflow Fails?

Fetch execution details with tasks, identify the failed task, summarize the error and retry count, then choose retry, rerun, skip, jump, terminate, or workflow-definition fix according to policy. Do not blindly retry terminal failures.

## 29. Non-Negotiable Invariants

- Every assistant tool call receives exactly one tool result.
- No side effect executes without validation and permission evaluation.
- Every action has an accountable principal and tenant.
- Deny beats allow.
- `dont_ask` never prompts.
- Hook-mutated input is revalidated before use.
- The sandbox must enforce the permission promise or the action must not run.
- Raw secrets are not model-visible.
- Regulated or cross-tenant data is not model-visible unless the provider, policy, principal, and purpose allow it.
- Large or sensitive outputs become artifacts with bounded previews.
- Background tasks emit at most one terminal model-visible notification.
- Resume produces provider-valid history.
- Child agents do not inherit broader permissions by accident.
- Plugin code is trusted only according to explicit policy and integrity checks.
- Skill code, command mappings, and validation rules are trusted only according to explicit policy and integrity checks.
- The user can interrupt foreground work.
- Workflow registration, schedule mutation, start, signal, retry, and termination are side effects and require policy checks.
- Conductor execution IDs, workflow versions, correlation IDs, and failed-task details are persisted as task metadata.
- Agentic work can supervise durable workflows, but it must not mutate workflow execution state outside typed workflow tools.
- Side-effecting Conductor tasks must run through harness-controlled policy enforcement or an equivalent trusted environment.
- Scheduled workflow runs must use explicit timezone, misfire policy, overlap policy, and idempotent correlation strategy.
- High-risk production actions require step-up, multi-party, or segregation-of-duties approval according to policy.

## 30. Testing Strategy

### Unit Tests

- Tool schema validation
- Permission rule ordering
- Principal resolution and delegation expiry
- Risk-tier and multi-party approval policy evaluation
- Hook mutation revalidation
- Sandbox path and resource checks
- Output redaction
- Data classification, residency, and retention checks
- Message graph repair
- Context package priority, trimming, and provenance rules
- Artifact preview generation
- Budget enforcement
- Cron syntax, timezone, misfire, overlap, and correlation-template validation
- Python sandbox limits, package allowlist, network denial, and artifact-only writes
- CLI command classification, argument allowlists, denied flags, identity guards, and output redaction
- Cloud cost normalization, currency handling, missing-tag behavior, delayed-export handling, and deterministic aggregation accuracy

### Integration Tests

- Model emits tool call, tool result returns, model continues
- Permission ask, user deny, model recovers
- Background task completes during later turn
- Provider fallback after partial stream
- Plugin tool loads and unloads
- Secret handle used by tool without model seeing secret
- High-risk action requires separate preparer and approver
- Workflow starts, waits, signals, and resumes
- Conductor workflow definition is generated, registered, started, monitored, and signaled
- Conductor schedule is created, paused, resumed, deleted, and fires through `start_workflow`
- Hybrid workflow pauses at `WAIT` or `HUMAN`, receives agent/user decision, then continues
- `agent_task` bridge completes exactly once and persists transcript/artifact references
- Global side-effect kill switch blocks writes while allowing safe reads
- Tenant quota throttles tool, workflow, and schedule execution without corrupting state
- Python-generated patch is stored as artifact, tested, reviewed, and applied only through normal file tools
- AWS, GCP, and Azure provider packs run identity checks before cost, inventory, utilization, and recommendation reads
- Cloud cost review workflow produces reproducible artifacts and can be scheduled with cron, timezone, and overlap protection
- IaC plan, Kubernetes diff, and cloud remediation plan paths produce artifacts before any apply or mutation

### Adversarial Tests

- Prompt injection asks model to reveal credentials
- Prompt injection asks model to cross tenant or repurpose data
- Tool input tries path traversal or resource alias bypass
- Shell command hides destructive operation in wrapper
- API call tries unapproved domain
- Hook returns invalid or malicious output
- Plugin declares conflicting tool name
- Duplicate task completion event
- Transcript corruption during resume
- Workflow definition tries duplicate task references or unauthorized task types
- Workflow retry would duplicate non-idempotent external work
- Conductor workflow tries direct side-effecting HTTP/MCP/system task outside harness proxy
- Workflow JSON or scheduled input contains raw secret-looking values
- Schedule misfire tries unbounded catch-up after outage
- Same principal attempts to prepare and approve a critical financial action
- Retry storm trips circuit breaker instead of amplifying downstream failure
- Disabled skill, plugin, or adapter cannot execute stale hooks or tools
- Python code attempts network, secret, filesystem escape, package install, fork bomb, or direct policy mutation
- Raw shell tries to bypass CLI wrappers through aliases, shell interpolation, hidden pipes, or wrapper scripts
- Cloud CLI profile points at a different account/project/subscription than the requested scope
- Cloud cost report includes confidential tags, account names, or resource names and must be redacted before export
- Cost-analysis prompt asks the model to make arithmetic claims that contradict deterministic tables

### Replay Tests

Record sessions and assert:

- Provider-facing messages are valid.
- Tool-use/result pairing is preserved.
- Redactions remain redacted.
- Permission decisions are reproducible.
- Compaction does not change unresolved obligations.

## 31. Production Operations And Rollout

Production readiness is not just "the agent works." It is whether the system can be safely introduced, observed, throttled, disabled, and investigated.

### Deployment Topology

Separate control-plane decisions from execution-plane side effects.

| Plane | Owns | Notes |
|---|---|---|
| Control plane | Sessions, policies, tool registry, model routing, schedules, approvals, audit, UI/API | Should be highly available and conservative |
| Execution plane | Sandboxes, browsers, workers, command runners, policy-proxied connectors, Conductor workers | Can be horizontally scaled and isolated by tenant or risk tier |
| Data plane | Transcripts, artifacts, telemetry, memory, embeddings, audit exports | Must enforce tenant, region, retention, and encryption policy |
| Secret plane | Vault, token exchange, scoped credential minting, revocation | Raw secrets never pass through model context |
| Workflow plane | Conductor or workflow backend, schedules, workflow execution state | Must call side-effecting tools through policy-enforced adapters |

### Rollout Modes

| Mode | Behavior | Exit Criteria |
|---|---|---|
| `offline_eval` | Run recorded tasks without side effects | Pass replay, policy, and redaction tests |
| `read_only` | Allow scoped reads and summaries | Low policy errors and acceptable retrieval quality |
| `draft_only` | Prepare emails, tickets, patches, plans, or workflow definitions without sending/applying | Human reviewers accept output quality |
| `supervised_action` | Side effects require explicit approval | Approval prompts are accurate and not excessive |
| `limited_autonomy` | Low-risk side effects allowed within budget and scope | No critical policy violations over burn-in window |
| `scheduled_supervised` | Schedules run but high-risk steps pause for approval | Misfire, overlap, and alert behavior validated |
| `scheduled_autonomous` | Approved recurring workflows run without per-run approval | Idempotency, rollback, and monitoring are proven |

### Observability

Every production run should be explainable by joining these identifiers:

- Tenant ID
- Principal ID
- Session ID
- Agent ID
- Tool call ID
- Side-effect ID
- Workflow ID
- Workflow version
- Schedule ID
- Schedule fire ID
- Artifact IDs
- Correlation ID
- Trace ID

Required metrics:

- Model latency, tool latency, workflow latency, and queue time.
- Tool success, failure, denial, timeout, and retry counts.
- Approval rate, denial rate, prompt timeout rate, and escalation rate.
- Secret redaction hits and policy block reasons.
- Token usage, model cost, tool cost, and workflow cost.
- Schedule fires, skipped overlaps, misfires, catch-up runs, and stuck executions.
- Background task age, orphaned task count, and terminal notification dedupe count.
- Tenant-level quotas and rate-limit rejections.

### Operational Controls

The operator must be able to stop damage faster than the agent can create it.

Required controls:

- Global kill switch for model calls.
- Global kill switch for side-effecting tools.
- Per-tool, per-skill, per-plugin, per-adapter disable switches.
- Tenant-level disable and quota controls.
- Pause all schedules.
- Pause all Conductor starts while allowing status reads.
- Revoke or rotate secret handles.
- Kill foreground/background task groups.
- Quarantine artifacts and memory writes.
- Force read-only mode.
- Export audit bundle for an incident.

### Evaluation Gates

Before enabling a production capability, require:

- Golden task replay for representative use cases.
- Policy replay against historical denied/approved actions.
- Red-team prompts for prompt injection, data exfiltration, and tool abuse.
- Workflow simulation with failed, timed-out, retried, skipped, and duplicate tasks.
- Schedule simulation for daylight-saving transitions, outage, overlap, and catch-up behavior.
- Human approval prompt review for clarity and reversibility.
- Cost and latency load test.
- Tenant isolation test.
- Rollback or disable drill.

### SLOs And Backpressure

Define SLOs per capability class, not one global number.

Examples:

- Read-only agent response latency.
- Tool execution latency.
- Approval prompt delivery time.
- Workflow start latency.
- Schedule fire delay.
- Background task notification delay.
- Policy decision latency.
- Artifact availability.

Backpressure rules:

- Queue instead of spawning unlimited tools, agents, browsers, or workflow starts.
- Apply tenant quotas before provider or backend quotas are exhausted.
- Use circuit breakers for failing adapters.
- Disable automatic retries during retry storms.
- Prefer degraded read-only mode over total outage.

### Ten-Pass Production Readiness Review

This score is for design-spec readiness: whether a competent team could implement, test, and operate the harness from the document. It is not a claim that an implementation is production-ready before code exists.

| Pass | Review Lens | Gap Found | Update Made | Score After Pass |
|---|---|---|---|---|
| 1 | Usability | Too conceptual for day-one users | Added production use-case matrix and user/operator needs | 8.4 |
| 2 | Power and breadth | No explicit default tool pack | Added day-one bundled tool pack across files, code, package managers, Python, process, CLI wrappers, HTTP, browser, data, cloud cost, cloud inventory, Kubernetes, IaC, observability, security, MCP/app connectors, workflows, agents, memory, audit, secrets, and telemetry | 8.8 |
| 3 | Deterministic workflows | Conductor integration needed stronger boundaries | Added policy-proxied Conductor side effects, Workflow IR, rendering rules, schedules, and agent bridge | 9.1 |
| 4 | Context management | Context was described but not packaged | Added typed context packages, priority, provenance, expiry, and trimming order | 9.3 |
| 5 | Filesystem handling | File semantics needed day-one coding/document safety | Added realpath, symlink, conflict, atomic write, binary, snapshot, lock, and secret-scan rules | 9.4 |
| 6 | Python self-evolution | No safe way for harness to write or test code | Added pinned Python sandbox, allowed libraries, artifact-only writes, tests, and self-evolution approval rule | 9.6 |
| 7 | Governance | Enterprise production actions needed accountability | Added principals, delegation, risk tiers, multi-party approvals, segregation of duties, and policy replay | 9.7 |
| 8 | Data and privacy | Regulated and cross-tenant data movement needed explicit rules | Added data governance, residency, purpose limitation, retention, legal hold, and audit export | 9.8 |
| 9 | Operations | Need kill switches, quotas, rollout, SLOs, and backpressure | Added deployment planes, rollout modes, metrics, controls, evaluation gates, and circuit breakers | 9.9 |
| 10 | Falsifiability | Needed concrete examples and MVP | Added worked production flows, MVP slice, exit criteria, and adversarial tests | 10.0 |

Final rating: **10/10 for a production implementation design spec**.

The remaining work is implementation, not design discovery: build the MVP slice, run the evaluation gates, and only then widen autonomy and tool coverage.

## 32. Operational Defaults

| Limit | Suggested Default |
|---|---|
| Max tool calls per turn | 25 |
| Max model loops per user request | 20 |
| Max concurrent read tools | 8 |
| Max concurrent side-effect tools | 1 |
| Max foreground tool runtime | 2 minutes |
| Max background task runtime | Policy-dependent |
| Max hook runtime | 5 seconds default, 30 seconds hard cap |
| Max hook output | 64 KB |
| Max model-visible tool output | 16 KB |
| Max artifact preview | 8 KB |
| Max raw transcript load | 50 MB unless indexed |
| Max child agents | 3 default, configurable |
| Default browser submit policy | Ask |
| Default secret reveal policy | Deny model-visible reveal |
| Default schedule timezone policy | Require explicit timezone |
| Default schedule misfire policy | `skip` |
| Default schedule overlap policy | `skip_if_running` |
| Max schedule catch-up runs | 1 unless explicitly approved |
| Default production rollout mode | `read_only` or `draft_only` |
| Max tenant concurrent tool calls | Policy-dependent quota |
| Max tenant scheduled fires per minute | Policy-dependent quota |
| Default retry storm circuit breaker | Disable automatic retries after threshold |
| Python sandbox network | Disabled by default |
| Python sandbox runtime | 60 seconds default, configurable |
| Python sandbox memory | 1 GB default, configurable |
| Python sandbox output | Artifact-only after preview cap |
| Python package installs | Disabled unless approved and pinned |
| Raw shell availability | Enabled only through policy; prefer typed tools and CLI wrappers |
| CLI output mode | Structured JSON when available; otherwise capped text plus artifact |
| Cloud identity guard | Required before every cloud provider operation |
| Cloud cost default lookback | 30 days interactive, 13 months scheduled/reporting when policy allows |
| Cloud cost max group-by dimensions | 3 default to avoid quota-heavy queries |
| Cloud cost export policy | Redacted artifact by default; external export requires approval |
| Cloud remediation policy | Plan-only by default; execution requires separate approval |
| Kubernetes production mutations | Deny unless explicit production escalation is active |
| IaC apply policy | Require approved plan artifact and workspace/account binding |

## 33. MVP Implementation Slice

The first production-capable slice should prove the safety loop before broadening domains.

### MVP Scope

Build one interactive agent plus one durable workflow path:

- One model provider.
- One tenant.
- One human principal type.
- One service-account principal type.
- Read-only resource adapter for files or documents.
- One side-effecting adapter with reversible or low-risk writes.
- Python sandbox with pinned day-one libraries and no network.
- Permission engine with allow, ask, deny, and policy replay.
- Artifact store with redacted previews.
- Secret broker with handles only.
- Conductor adapter for register/start/status/signal.
- One scheduled workflow with cron, timezone, overlap policy, and correlation ID.
- Global side-effect kill switch.
- Audit export for a single session/workflow.

### MVP Use Case

Recommended MVP: scheduled support-ticket triage.

Why:

- It exercises real data governance and tenant scoping.
- It supports draft-only and supervised-action rollout.
- It can use Conductor scheduling without requiring dangerous production mutations.
- It has clear human evaluation: ticket summary quality, routing accuracy, and draft usefulness.
- It can add low-risk side effects later, such as tagging a ticket, before refunds or sends.

MVP flow:

1. Schedule fires hourly.
2. Conductor starts ticket triage workflow with schedule principal.
3. Workflow reads new tickets through policy-proxied adapter.
4. Agent summarizes and classifies tickets.
5. Agent drafts replies and suggested tags as artifacts.
6. Human approves applying tags.
7. Harness applies tags with idempotency key.
8. Audit bundle records principal, schedule fire, workflow ID, model calls, tool calls, approvals, artifacts, and policy decisions.

### Explicitly Out Of MVP

- Autonomous production remediation.
- Payments, refunds, deletes, or irreversible customer actions.
- Multi-tenant self-service plugin marketplace.
- Browser form submission.
- Physical device control.
- Cross-region regulated data movement.
- Multi-model fallback.
- Recursive subagent delegation.

### MVP Exit Criteria

- 100 recorded sessions replay provider-valid.
- 100% of tool calls have exactly one result.
- 100% of side effects have principal, tenant, policy version, and audit event.
- Red-team prompt-injection suite cannot cause external sends, secret reveal, or cross-tenant reads.
- Python sandbox cannot access network, raw secrets, protected files, or mutate policy directly.
- Schedule misfire, overlap, pause, and kill-switch tests pass.
- Human reviewers accept draft quality above agreed threshold.
- Operators can export an audit bundle and explain every side effect.

## 34. Build Order

Build the smallest safe harness first, then widen capabilities.

1. Typed message model and transcript store.
2. Single model provider adapter.
3. Tool registry with one read-only tool.
4. Tool-use/result pairing and synthetic failures.
5. Permission engine with allow, ask, deny.
6. Resource manager and basic sandbox.
7. Artifact store, output truncation, and filesystem-safe write path.
8. Context packages, compaction, and resume repair.
9. Python sandbox with pinned libraries and artifact-only writes.
10. Principal resolver and tenant isolation.
11. Observability, audit bundle export, and kill switches.
12. Side-effecting tools with approvals.
13. Task manager for long-running work.
14. Skill loader with plugin-grade trust controls.
15. Conductor skill adapter.
16. Workflow policy analyzer and Conductor registration/start/monitor tools.
17. Cron schedule model and schedule management tools.
18. Plugin loader with integrity policy.
19. Subagents with scoped tools.
20. Harness-controlled `agent_task` bridge.
21. Hybrid durable workflow plus agentic leaf execution.
22. Multi-provider fallback.
23. Advanced resource adapters.

## 35. Build-Vs-Buy Decisions

| Area | Build | Buy or Integrate |
|---|---|---|
| Conversation engine | Build | Core differentiator |
| Permission engine | Build | Must match product policy |
| Sandbox | Integrate OS/container/cloud controls | Do not fake isolation |
| Python runtime | Build policy wrapper; integrate container/microVM and pinned packages | The harness owns limits, artifacts, and approvals |
| Workflow engine | Integrate if durable workflows matter | Hard to build correctly |
| Durable workflow backend | Integrate Conductor through the skill adapter | Provides durable execution, retries, waits, and status APIs |
| Workflow scheduler | Use Conductor or Orkes schedules when available; otherwise integrate an external scheduler | Harness must still own policy and start path |
| Secret storage | Integrate platform vault | Avoid custom crypto |
| Observability | Integrate telemetry stack | Standard problem |
| Plugin marketplace | Start minimal | Mature supply chain later |
| Browser automation | Integrate established driver | Keep policy layer in harness |
| Vector search | Integrate | Harness owns retrieval policy |

## 36. Design Checklists

### Before Exposing A Tool

- What resources can it touch?
- What capabilities does it require?
- Is it read-only, reversible, idempotent, and concurrency-safe?
- What is the worst plausible side effect?
- What permission prompt should the user see?
- What sandbox enforces the promise?
- What output can be too large or sensitive?
- How does it fail?
- Can it be retried safely?
- What audit record is needed?

### Before Adding A Resource Adapter

- How are resource IDs resolved?
- Can aliases bypass policy?
- What snapshot or version ID prevents stale writes?
- What locks or conflict checks are needed?
- What credentials are used?
- How are rate limits and quotas handled?
- What is the smallest safe capability set?

### Before Adding A Plugin

- Is the source trusted?
- Is the version pinned?
- Are manifests validated?
- Are namespaced tools enforced?
- Can the plugin add hooks?
- Can the plugin access secrets?
- How is disable or uninstall handled?

### Before Adding A Skill

- Is the source trusted under managed policy?
- Is the skill version, commit, digest, or signature pinned?
- Are path ownership and file permissions safe?
- Are command allowlists narrow and validated?
- Are skill-provided tools and hooks namespaced?
- Can the skill access secrets or execute local commands?
- How is disable or unload handled?

### Before Scheduling A Workflow

- Is the workflow definition already registered and version-pinned?
- Is the cron expression valid?
- Is the timezone explicit?
- What happens during daylight-saving transitions?
- What is the misfire policy?
- What is the overlap policy?
- Is each scheduled run idempotent?
- Does the input template contain only secret handles, not raw secrets?
- Does the schedule start path reuse normal workflow policy analysis?

### Before Allowing Python Code

- Is the package set pinned and scanned?
- Is network disabled or explicitly domain-scoped?
- Are input artifacts mounted read-only?
- Are outputs restricted to artifact directory?
- Are CPU, memory, time, process, and output limits enforced?
- Does the code need secrets, and if so can it use handles instead of raw values?
- Does generated code produce tests and a patch artifact rather than mutating trusted runtime state?
- Is the run reproducible from stored code, inputs, packages, and environment metadata?

### Before Enabling Autonomy

- What is the explicit goal?
- What resources are in scope?
- What side effects are allowed?
- What is the cost and time budget?
- What requires human approval?
- How can the user stop it?
- What final report proves what happened?

## 37. Mental Model

A generic agent harness is not a chatbot wrapper. It is a transaction coordinator for model-suggested operations.

For every action, it answers:

- What did the model ask to do?
- Is the request valid?
- Which resource and capability does it require?
- Is the user or policy willing to allow it?
- Can the sandbox enforce the allowed scope?
- What exactly executed?
- What changed?
- What does the model see next?
- Can the system recover if interrupted now?

If those questions have structured answers, the harness can safely grow from simple chat plus tools into a general-purpose agent runtime.
