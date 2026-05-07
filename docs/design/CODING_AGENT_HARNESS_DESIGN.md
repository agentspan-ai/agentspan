# How To Build A Coding Agent Harness

This document describes a practical architecture for a coding agent or agent harness. It is written as a standalone design: the goal is to build a runtime that can hold a conversation, call tools safely, edit files, run commands, delegate work, recover from long contexts, and persist enough state to resume or audit behavior.

The central idea is simple:

> Treat the model as a planner and language interface. Treat the harness as the operating system that validates, authorizes, executes, records, and recovers every side effect.

## 1. Design Goals

A good coding-agent harness should optimize for these properties:

- **Correctness:** Every model-visible tool result must correspond to a real tool call or a real synthetic failure.
- **Safety:** File writes, shell commands, network calls, and delegation require explicit policy checks before execution.
- **Recoverability:** A session should survive interruptions, retries, long outputs, background tasks, and context limits.
- **Composability:** Tools, hooks, permissions, UI, storage, and model providers should be replaceable modules.
- **Observability:** Every turn, tool decision, task transition, and error should be inspectable.
- **Prompt stability:** Avoid needless changes to system prompts, tool schemas, and serialized history because that breaks provider-side caching.
- **Human control:** The user must be able to approve, reject, interrupt, background, resume, and inspect work.

## 2. High-Level Architecture

Use these major modules:

```text
CLI or API entrypoint
  -> Session bootstrap
  -> Input processor
  -> Conversation engine
  -> Model client
  -> Tool orchestrator
  -> Permission engine
  -> Sandbox and process runner
  -> Task manager
  -> Persistence layer
  -> Renderer or event stream
```

The harness should not be a single large loop. Keep the model loop small and make everything else explicit services.

### Core Responsibilities

| Module | Responsibility |
|---|---|
| Entrypoint | Parse flags, initialize settings, load tools, create session state |
| Input processor | Convert user input, slash commands, pasted files, and metadata into typed messages |
| Conversation engine | Own turn lifecycle, context preparation, model streaming, tool follow-up loops |
| Model client | Serialize messages and tools into provider API requests; normalize streaming responses |
| Tool registry | Holds built-in, plugin, MCP, and deferred tools |
| Tool orchestrator | Validates and runs tool calls, manages parallelism, emits progress and results |
| Permission engine | Decides allow, deny, or ask for each side effect |
| Sandbox | Enforces filesystem and network boundaries below the permission layer |
| Task manager | Tracks background shell commands, subagents, remote tasks, and long-running jobs |
| Persistence | Writes transcripts, task output, side-channel metadata, and resumable state |
| Renderer or SDK stream | Presents messages, progress, diffs, approvals, and task notifications |

## 3. Message Model

Use a typed message ledger. Do not pass loose strings through the system.

Recommended message types:

```ts
type Message =
  | UserMessage
  | AssistantMessage
  | ToolProgressMessage
  | AttachmentMessage
  | SystemMessage
  | TombstoneMessage;

type UserMessage = {
  type: "user";
  id: string;
  parentId?: string;
  content: TextBlock[] | ToolResultBlock[] | MixedContent[];
  isMeta?: boolean;
  sourceToolCallId?: string;
};

type AssistantMessage = {
  type: "assistant";
  id: string;
  parentId?: string;
  content: TextBlock[] | ToolUseBlock[] | ThinkingBlock[];
  usage?: TokenUsage;
  requestId?: string;
  apiError?: string;
};

type ToolUseBlock = {
  type: "tool_use";
  id: string;
  name: string;
  input: unknown;
};

type ToolResultBlock = {
  type: "tool_result";
  toolUseId: string;
  content: unknown;
  isError?: boolean;
};
```

Rules:

- Every assistant tool use must eventually receive exactly one matching tool result.
- Progress messages are UI or SDK events, not durable conversation messages unless explicitly needed.
- Synthetic failures are valid tool results when execution cannot happen.
- Record parent-child relationships so resumes can reconstruct a linear chain.
- Preserve the raw assistant message sent by the provider; clone only for UI or SDK display transformations.

## 4. Conversation Engine

The conversation engine owns the turn lifecycle. It should be implemented as an async generator or event stream so callers can consume partial output, progress, approvals, and final state.

### Turn Flow

```text
submit user input
  -> process input into messages
  -> build model-ready context
  -> compact or trim history if needed
  -> call model with tools
  -> stream assistant messages
  -> collect tool_use blocks
  -> execute tools
  -> append tool_result messages
  -> repeat while the model requests tools
  -> run stop hooks
  -> persist final transcript
```

### Engine State

Each turn should carry a small explicit state object:

```ts
type TurnState = {
  messages: Message[];
  context: ToolUseContext;
  turnCount: number;
  compaction: CompactionState;
  tokenBudget: TokenBudgetState;
  recovery: RecoveryState;
  pendingSummaries: Promise<Message | null>[];
};
```

Avoid global mutable state inside the engine. When something must be mutable, place it in the state object or in a well-named session store.

### Loop Exit Reasons

Return a structured terminal reason:

```ts
type TerminalReason =
  | "completed"
  | "aborted"
  | "blocked_by_permission"
  | "blocked_by_hook"
  | "context_limit"
  | "model_error"
  | "max_turns"
  | "budget_exceeded";
```

This makes API callers and UI flows easier to implement.

## 5. Tool Contract

Tools are the main boundary between model intent and real side effects. Every tool should implement the same contract.

```ts
type Tool<Input, Output, Progress = unknown> = {
  name: string;
  aliases?: string[];
  searchHint?: string;
  description(input: Input, context: ToolDescriptionContext): Promise<string>;
  inputSchema: Schema<Input>;
  inputJsonSchema?: JsonSchema;
  outputSchema?: Schema<Output>;
  prompt(context: ToolPromptContext): Promise<string>;

  validateInput?(input: Input, context: ToolUseContext): Promise<ValidationResult>;
  checkPermissions(input: Input, context: ToolUseContext): Promise<PermissionResult>;
  call(
    input: Input,
    context: ToolUseContext,
    authorize: CanUseTool,
    parentMessage: AssistantMessage,
    onProgress?: (progress: Progress) => void,
  ): Promise<ToolResult<Output>>;

  isEnabled(): boolean;
  isReadOnly(input: Input): boolean;
  isConcurrencySafe(input: Input): boolean;
  isDestructive?(input: Input): boolean;
  isOpenWorld?(input: Input): boolean;
  requiresUserInteraction?(): boolean;
  interruptBehavior?(): "cancel" | "block";
  maxResultSizeChars: number;
  shouldDefer?: boolean;
  alwaysLoad?: boolean;
  strict?: boolean;

  backfillObservableInput?(input: Record<string, unknown>): void;
  preparePermissionMatcher?(input: Input): Promise<(pattern: string) => boolean>;
  toModelResult(output: Output, toolUseId: string): ToolResultBlock;
  toSafetyClassifierInput(input: Input): unknown;
  toDisplaySummary?(input: Partial<Input>): string | null;
  toActivityDescription?(input: Partial<Input>): string | null;
};
```

Default tool behavior should fail closed:

- `isConcurrencySafe` defaults to `false`.
- `isReadOnly` defaults to `false`.
- `isDestructive` defaults to `false`, but destructive tools should explicitly mark themselves.
- `checkPermissions` defaults to passing through the general permission layer, not bypassing it.
- `toSafetyClassifierInput` defaults to empty; security-relevant tools must override it.

Tool metadata is part of runtime correctness, not just UI polish. The registry should use tool metadata to decide prompt generation, permission-rule matching, deferred loading, output truncation, activity display, transcript rendering, and safety-classifier input. Keep model-facing result mapping separate from human-facing rendering.

External tools should be namespaced or otherwise disambiguated from built-ins. Filter denied external tools before the model sees them, then sort built-in tools and external tools deterministically so prompt caching remains stable. Built-ins should win name conflicts unless an explicit replacement policy exists.

## 6. Tool Execution Pipeline

Every tool call should pass through the same ordered pipeline:

```text
find tool
  -> parse input schema
  -> validate semantic input
  -> run pre-tool hooks
  -> decide permission
  -> start telemetry span
  -> execute tool
  -> enforce output budget
  -> map output to model-facing tool_result
  -> run post-tool hooks
  -> persist or emit result
```

Important details:

- Schema errors should be returned to the model as tool errors, not thrown as process errors.
- Validation errors should include actionable guidance for retry.
- Permission denials should be model-visible tool results.
- Tool exceptions should be wrapped into tool result errors so the model can recover.
- Long outputs should be saved to disk with a short preview, unless the tool has its own safe truncation behavior.
- A tool should never mutate the original model response object. Clone if UI needs derived fields.

## 7. Parallel Tool Execution

Allow parallel tool execution only for tools that explicitly declare themselves safe.

Execution rules:

- Consecutive read-only, concurrency-safe calls may run in parallel.
- Writes, shell commands, edits, sends, and destructive operations run serially.
- A non-concurrency-safe tool requires exclusive access.
- Results should be emitted in a stable order even if internal execution is parallel.
- If one shell command in a parallel batch fails, cancel sibling shell commands because they often have implicit dependencies.
- Independent read failures should not cancel other reads.

Basic orchestration:

```ts
for (const batch of partitionToolCalls(toolUses)) {
  if (batch.concurrent) {
    yield* runConcurrently(batch.calls, maxConcurrency);
  } else {
    yield* runSerially(batch.calls);
  }
}
```

## 8. Streaming Tool Execution

If the provider streams tool calls before the assistant message is complete, start tools as soon as their full input is available.

Benefits:

- Lower latency for read/search/fetch operations.
- Better UI progress during long turns.
- Earlier detection of permission prompts.

Hazards to handle:

- If the model request falls back or retries, discard tool results from the abandoned attempt.
- If a streamed tool is interrupted, create a synthetic tool result for the original tool use ID.
- If the user interrupts, cancel tools whose `interruptBehavior` is `cancel`; block interruption for tools that must finish atomically.
- Never emit orphan tool results for assistant messages that were tombstoned.
- If provider streaming emits assistant fragments with the same message ID, preserve them separately in the transcript but merge them for provider requests.
- If an API response includes tool inputs as JSON strings, normalize them into objects before validation and execution.
- If a streamed assistant message is cloned for observable output, keep the provider-bound copy byte-stable for prompt-cache and signature validity.

## 9. Permission System

The permission system should return one of three decisions:

```ts
type PermissionDecision =
  | { behavior: "allow"; updatedInput?: unknown; reason: PermissionReason }
  | { behavior: "deny"; message: string; reason: PermissionReason }
  | { behavior: "ask"; message: string; suggestions?: PermissionUpdate[]; reason: PermissionReason };
```

Use layered checks:

```text
abort check
  -> blanket deny rules
  -> blanket ask rules, except sandbox-auto-allowed shell commands
  -> tool-specific permission checks
  -> tool-specific deny result
  -> required-user-interaction ask result
  -> tool-specific ask result
  -> bypass-resistant safety checks
  -> bypass or plan-bypass allow, if configured
  -> explicit allow rules
  -> permission mode policy
  -> automated safety classifier, if enabled
  -> permission_request hooks
  -> user prompt, if available
  -> deny if prompts are unavailable
```

Order matters. Allow rules do not outrank deny rules, explicit ask rules, tool-specific asks, required human interaction, or safety checks. A dangerous operation should not become allowed just because the session is in bypass mode; bypass means skip ordinary prompts, not disable safety gates.

### Permission Modes

Support these modes:

| Mode | Behavior |
|---|---|
| `default` | Ask for side effects unless allowed by rules |
| `plan` | Permit planning and reading; block writes and commands until approved |
| `accept_edits` | Allow file edits in trusted paths; ask for commands and risky actions |
| `auto` | Use automated checks for routine actions; ask only when checks cannot decide |
| `dont_ask` | Convert asks into denials |
| `bypass` | Allow everything that the sandbox permits; make this visibly dangerous |

### Permission Rules

Represent rules as structured values, not raw strings internally:

```ts
type PermissionRule = {
  source: "policy" | "project" | "user" | "cli" | "session";
  behavior: "allow" | "deny" | "ask";
  toolName: string;
  pattern?: string;
};
```

Examples:

- Allow a read tool globally.
- Allow shell commands matching `git status`.
- Deny writes to configuration directories.
- Ask for all network fetches outside an allowlist.

## 10. Sandboxing

Permissions are advisory; sandboxing is enforcement.

Use an OS-level or runtime-level sandbox for:

- Filesystem read/write restrictions.
- Network domain restrictions.
- Process execution restrictions.
- Protected configuration paths.
- Sensitive credentials and key material.

Principles:

- Always allow the current workspace and a controlled temp directory only as needed.
- Deny writes to harness settings, plugin directories, skill directories, and authentication storage.
- Treat bare repositories, symlinks, and generated hooks as sandbox escape risks.
- Network allowlists should be explicit.
- A user approval to run outside the sandbox must be a separate, visible decision.

## 11. Shell Command Runner

Shell execution needs special handling because commands can be long-running, interactive, huge-output, or destructive.

Design the command runner around a `ShellCommand` object:

```ts
type ShellCommand = {
  result: Promise<ExecResult>;
  status: "running" | "backgrounded" | "completed" | "killed";
  background(taskId: string): boolean;
  kill(): void;
  cleanup(): void;
  taskOutput: TaskOutput;
};
```

Required behavior:

- Stream stdout and stderr to a task output file.
- Keep only bounded previews in memory.
- Enforce command timeout.
- Enforce maximum output size.
- Support backgrounding without losing output.
- Kill the whole process tree, not just the parent process.
- Detect likely interactive prompts from stalled output and notify the model.
- Do not treat background completion notifications as user text; use structured task notification messages.
- Use exit events that do not wait indefinitely on inherited stdio from grandchildren.
- On normal interruption, either kill or background according to tool policy; do not leave an untracked process.
- Preserve file encoding and line endings when a shell command is converted into an internal safe edit path.
- Keep the shell approval description user-visible so prompts explain intent, not just raw command text.

## 12. Task Manager

Long-running work should be represented as tasks.

```ts
type TaskState = {
  id: string;
  type: "shell" | "agent" | "remote" | "workflow";
  status: "pending" | "running" | "completed" | "failed" | "killed";
  description: string;
  startTime: number;
  endTime?: number;
  outputFile: string;
  toolUseId?: string;
  notified: boolean;
};
```

Task manager responsibilities:

- Register tasks atomically.
- Update task status without side effects inside state reducers.
- Provide `kill(taskId)`.
- Provide `readOutput(taskId, offset)`.
- Emit a single completion notification.
- Evict output after safe retention windows.
- Keep background tasks alive when the foreground turn is interrupted, unless explicitly tied to parent cancellation.
- Distinguish foreground-running tasks from backgrounded tasks. Foreground tasks may be backgrounded in place; do not re-register them or duplicate task-start events.
- Mark `notified` atomically before enqueueing terminal notifications so races cannot produce duplicate model-visible task messages.
- When a task reaches a terminal state, update status before slow embellishments such as summaries, handoff classification, git inspection, or cleanup.
- Run cleanup callbacks outside state updaters.
- Kill child background shell or monitor tasks owned by a subagent when that subagent exits.
- Treat stall detection as advisory: notify only when output stops growing and the tail looks like an interactive prompt.

## 13. Subagents And Delegation

Subagents are specialized sessions launched by the main session.

Support two forms:

- **Synchronous subagent:** Parent waits for completion and receives a concise result.
- **Background subagent:** Parent receives a task ID immediately and gets a structured notification later.

Subagent inputs:

```ts
type SpawnAgentInput = {
  description: string;
  prompt: string;
  agentType?: string;
  model?: string;
  runInBackground?: boolean;
  allowedTools?: string[];
  cwd?: string;
  isolation?: "same_workspace" | "worktree" | "remote";
};
```

Subagent rules:

- Give each agent a stable ID.
- Give each agent its own transcript.
- Give each agent its own abort controller.
- Async agents should not inherit foreground cancellation unless explicitly linked.
- Agents that cannot show permission prompts must auto-deny unresolved asks.
- Parent session permissions should not leak into subagents unless explicitly passed.
- Read-only agents should get read/search tools only.
- Editing agents should work in an isolated worktree when parallel edits are possible.
- Background agents should report progress through task state, not ad hoc chat.
- Build the subagent tool pool under the subagent's effective permission mode. If an `allowedTools` override is provided, replace session allow rules for that agent instead of leaking parent session approvals wholesale.
- Filter incomplete parent tool calls before forking context into a subagent. A subagent request must not inherit assistant tool-use blocks that have no matching tool result.
- Scope agent-specific tool servers, hooks, and preloaded skills to the agent lifecycle; connect or register them at start and clean them up in `finally`.
- Persist sidechain transcripts and agent metadata while the agent runs so background or resumed agents remain inspectable.
- For prompt-cache-sensitive forked agents, use byte-stable prefix construction: same parent system prompt, same tool definitions, placeholder tool results for all sibling fork tool uses, then a per-child directive.
- Prevent recursive fork spawning when a forked child still has the spawn tool for cache-stability reasons.

## 14. Worktree Isolation

For coding agents, worktree isolation is the safest way to parallelize file edits.

Flow:

```text
spawn agent
  -> create branch/worktree
  -> run agent with cwd set to worktree
  -> inject path-translation notice when inherited context mentions parent paths
  -> require agent to read before editing
  -> on completion, detect changes
  -> transition task status before cleanup
  -> keep worktree if changed
  -> delete worktree if unchanged
  -> report path and branch if kept
```

Do not silently merge worktree changes. Integration should be explicit.

Worktree cleanup must be idempotent. If change detection is unavailable, the safe default is to keep the worktree and report the path. If deleting a worktree would discard uncommitted files or commits, require an explicit discard flag and a user-visible warning.

## 15. Context Management

Context management should be proactive and reactive.

### Proactive Measures

- Estimate token count before each model request.
- Compact old history before hitting provider limits.
- Replace large tool results with stable references to persisted files.
- Drop stale or irrelevant environment context for narrow subagents.
- Prefer summaries for completed background tasks instead of full logs.

### Reactive Measures

- If the provider returns a context-length error, try a one-time compaction retry.
- If output token limit is hit, retry with a higher output limit once if supported.
- If retry still fails, inject a meta continuation prompt up to a bounded count.
- Never run stop hooks on provider errors because hooks can create retry loops.

### Prompt Cache Stability

To preserve provider-side prompt caching:

- Do not mutate assistant messages that will be replayed to the model.
- Keep system prompt construction deterministic.
- Keep tool schema ordering stable.
- Keep placeholder messages byte-identical when forking contexts.
- Record replacement decisions so resumed sessions make the same context substitutions.

## 16. Hooks

Hooks let users and integrations add policy, context, and validation without modifying core runtime.

Useful hook events:

| Event | Purpose |
|---|---|
| `session_start` | Add environment context or block startup |
| `user_prompt_submit` | Validate or enrich user input |
| `pre_tool_use` | Block, modify, or annotate tool input |
| `permission_request` | Auto-approve or deny prompts in headless contexts |
| `post_tool_use` | Audit results or trigger follow-up work |
| `stop` | Validate final assistant response before ending a turn |
| `subagent_start` | Add context to child agents |
| `subagent_stop` | Validate child result |

Hook rules:

- Hooks must have timeouts.
- Hook failures should fail closed only when configured to do so.
- Hook outputs must be structured.
- Hook-added context should be visibly labeled.
- Hooks should receive an abort signal.
- Hooks that execute local commands require workspace trust. In non-interactive/headless contexts, trust must be explicit in configuration.
- Hook input should include session ID, transcript path, current working directory, permission mode, and agent ID/type when running inside a subagent.
- Validate JSON hook output against an event-specific schema. Treat unstructured stdout as display/audit text, not as authorization.
- Permission hooks may return allow, ask, deny, updated input, or a reason; those decisions still flow through the permission pipeline rather than bypassing it.
- Async hooks must be registered as background work with bounded output and cleanup. If an async stop hook later blocks continuation, reinsert it as a structured task notification.
- Session-end hooks need a much shorter timeout than normal tool hooks because shutdown must not hang.
- Policy can restrict hooks to admin-trusted plugin or managed sources; user-controlled hooks should be skipped under such policies.

## 17. Model Client

The model client should be a narrow adapter.

Responsibilities:

- Convert typed messages into provider request format.
- Convert tool definitions into provider tool schemas.
- Stream normalized events back to the engine.
- Attach model, effort, thinking, max tokens, and beta flags.
- Track usage and request IDs.
- Retry transient failures with backoff.
- Support fallback models without leaking orphan tool calls.
- Normalize provider API errors into assistant error messages.
- Strip or transform message fields that are not valid for the selected provider, model, or beta set.
- Validate message/media limits before the request when possible, and surface recoverable errors as structured assistant messages.
- Preserve provider-specific thinking blocks only for the valid trajectory, and drop or summarize them when replay would violate provider rules.

Keep provider-specific concerns out of the tool and permission layers.

## 18. Persistence

Persist enough information to answer four questions:

- What did the user ask?
- What did the model decide?
- What side effects were approved and executed?
- How can this session resume safely?

Recommended files:

```text
sessions/{sessionId}.jsonl
sessions/{sessionId}/subagents/{agentId}.jsonl
tasks/{taskId}.log
tasks/{taskId}.meta.json
content-replacements/{sessionId}.jsonl
```

Transcript rules:

- Use append-only JSONL for normal writes.
- Include message IDs and parent IDs.
- Do not persist ephemeral progress ticks.
- Persist compact boundaries and content replacement records.
- Put large task outputs in separate files.
- Cap raw transcript read size on resume to avoid out-of-memory failures.
- Use tombstones or rewrite only for small files when recovering from orphaned streamed messages.
- Model streaming can create a DAG, not a simple linked list: parallel tool-use assistant fragments may share one provider message ID while their tool results point to different assistant UUIDs. Resume logic must recover sibling assistant fragments and sibling tool results, not just follow one parent chain.
- Detect parent-chain cycles and return a valid partial transcript instead of recursing forever.
- Store file-history snapshots and content-replacement records so edit conflict checks and large-result substitutions survive resume.
- On resume, migrate legacy attachment shapes, discard invalid permission-mode fields, filter unresolved tool uses, filter orphaned thinking-only assistant messages, and remove whitespace-only assistant messages.
- If a session was interrupted mid-turn, append a synthetic continuation prompt or sentinel message so the loaded conversation is provider-valid and can continue safely.

## 19. Renderer And API Events

Do not couple the engine to a terminal UI.

Emit normalized events:

```ts
type RuntimeEvent =
  | { type: "message"; message: Message }
  | { type: "progress"; taskId?: string; toolUseId?: string; data: unknown }
  | { type: "permission_request"; request: PermissionPrompt }
  | { type: "task_started"; task: TaskState }
  | { type: "task_updated"; task: TaskState }
  | { type: "error"; error: RuntimeError }
  | { type: "done"; reason: TerminalReason };
```

Then build terminal UI, JSON streaming, SDK callbacks, or web UI on top of those events.

## 20. Memory And Repository Context

A coding agent needs context, but context should be scoped.

Include:

- Current working directory.
- Relevant project instructions.
- Git status summary.
- Recently changed files.
- User-selected files or pasted content.
- Tool and permission capabilities.

Avoid:

- Full repository dumps.
- Stale git status in subagents that can query fresh state.
- Large logs unless the current task requires them.
- Hidden policy text that affects behavior but cannot be audited.

## 21. Implementation Plan

Build the harness in phases.

### Phase 1: Single-Turn Read-Only Agent

Deliver:

- CLI or API entrypoint.
- Typed message ledger.
- Model client streaming text.
- Read, glob, grep tools.
- Tool schema validation.
- Transcript JSONL.

Exit criteria:

- The agent can answer repository questions with read-only tools.
- Every tool use has a matching result.
- Sessions can be inspected after completion.

### Phase 2: Safe File Editing

Deliver:

- File write and patch tools.
- Diff rendering.
- Permission rules.
- Plan mode.
- Workspace write restrictions.
- Before-and-after file snapshots.

Exit criteria:

- The agent can edit files only after approval or explicit allow rules.
- Rejected edits are returned to the model as tool errors.
- Changed files are auditable.

### Phase 3: Shell Execution

Deliver:

- Shell command tool.
- Sandbox integration.
- Timeout and output limits.
- Background command tasks.
- Process-tree kill.
- Interactive prompt watchdog.

Exit criteria:

- Commands can run, be interrupted, be backgrounded, and be inspected.
- Huge output does not exhaust memory.
- Dangerous commands require explicit approval.

### Phase 4: Long Context And Recovery

Deliver:

- Token estimation.
- Tool result budget.
- Manual and automatic compaction.
- Provider error recovery.
- Max-turn and budget limits.

Exit criteria:

- Long sessions continue without hitting context limits in normal use.
- Provider errors do not create invalid message histories.

### Phase 5: Subagents

Deliver:

- Agent definitions.
- Spawn-agent tool.
- Agent-specific tool pools.
- Background task notifications.
- Subagent transcripts.
- Worktree isolation.

Exit criteria:

- The main agent can delegate bounded work.
- Background agents survive foreground interruption.
- Parallel edits are isolated.

### Phase 6: Hooks And Plugins

Deliver:

- Hook events.
- Plugin-loaded tools.
- External tool servers.
- Tool discovery for deferred tools.
- Policy-managed settings.

Exit criteria:

- Integrations can add tools and policy without modifying the engine.
- Headless mode can still resolve permissions via hooks or fail closed.

## 22. Minimal Interfaces

These interfaces are enough to start implementation.

```ts
type HarnessConfig = {
  cwd: string;
  model: string;
  tools: Tool<any, any>[];
  permissionMode: PermissionMode;
  maxTurns: number;
  maxBudgetUsd?: number;
};

type ToolUseContext = {
  cwd: string;
  sessionId: string;
  abortController: AbortController;
  messages: Message[];
  tools: Tool<any, any>[];
  permissionContext: PermissionContext;
  taskManager: TaskManager;
  store: StateStore;
  persist: Persistence;
};

type ConversationEngine = {
  submit(input: UserInput): AsyncGenerator<RuntimeEvent, TerminalReason>;
};

type TaskManager = {
  register(task: TaskState): void;
  update(taskId: string, patch: Partial<TaskState>): void;
  kill(taskId: string): Promise<void>;
  readOutput(taskId: string, offset?: number): Promise<OutputChunk>;
};
```

## 23. Non-Negotiable Invariants

Keep these invariants under test:

- A model-visible tool result always references an existing assistant tool use.
- No tool call runs before schema validation and permission decision.
- Non-read-only tools do not run concurrently unless explicitly allowed.
- A denied permission is represented as a tool error, not as a silent drop.
- Background task completion emits at most one notification.
- Interrupting a turn cannot leave unmatched tool uses in the next request.
- Resuming a transcript reconstructs the same provider-facing message order.
- Large outputs are bounded in memory.
- Sandbox restrictions remain active even when permission rules allow an action.
- Subagents do not inherit broader permissions than intended.

## 24. Testing Strategy

Test at four levels:

- **Unit tests:** Tool validation, permission matching, path resolution, command parsing, message normalization.
- **Integration tests:** Model loop with fake provider responses and real tool execution in a temp workspace.
- **Replay tests:** Recorded transcripts replay to the same provider-facing request shape.
- **Safety tests:** Dangerous commands, symlink paths, protected config writes, network denials, interrupted tool calls.

Useful fake provider scripts:

- Text-only response.
- One tool call then final response.
- Multiple parallel read tool calls.
- Invalid tool input.
- Tool call followed by provider fallback.
- Prompt-too-long error.
- Max-output-token error.
- Streaming assistant message with partial tool calls.

## 25. Common Failure Modes

Avoid these design mistakes:

- Letting tools throw raw errors that skip tool-result generation.
- Letting UI permission prompts be the only permission mechanism.
- Persisting progress messages as transcript chain participants.
- Storing all command output in memory.
- Reusing parent permissions in subagents by accident.
- Running shell commands and file edits in parallel.
- Mutating assistant messages before replaying them to the model.
- Treating background task notifications as unstructured text.
- Running hooks after provider API errors.
- Building tool schemas dynamically in a way that changes order across turns.

## 26. Recommended Build Order

If you are writing this from scratch, implement in this exact order:

1. Typed messages and transcript writer.
2. Model streaming adapter with no tools.
3. Tool registry and read-only tools.
4. Tool execution pipeline with schema errors as tool results.
5. Permission engine with `default`, `plan`, and `dont_ask`.
6. File edit tool with diff approval.
7. Shell runner with timeouts, task output files, and process-tree kill.
8. Background task manager and notifications.
9. Context compaction and large-result replacement.
10. Subagents with isolated permissions.
11. Worktree isolation.
12. Hooks and external plugins.
13. Full replay and safety test suite.

## 27. The Mental Model

The harness is not a chatbot wrapper. It is a transaction coordinator for model-suggested operations.

For every turn, the harness must answer:

- What exactly did the model ask to do?
- Is the input valid?
- Is the operation allowed?
- Where will it run?
- How is it cancelled?
- How is output bounded?
- What is persisted?
- What does the model see next?
- What does the user see now?
- How can this be resumed or audited later?

If those questions have explicit code paths, the harness will be robust. If any of them are implicit, the agent will eventually corrupt context, execute unsafe actions, lose state, or become impossible to debug.

## 28. Complete Tool Inventory

Separate model-facing tools from internal runtime services. The model should see only tools that are useful for planning and execution. Internal services should not be exposed unless the model genuinely needs to operate them.

### Essential Model-Facing Tools

| Tool | Purpose | Permission Level | Concurrency |
|---|---|---|---|
| `read_file` | Read bounded file ranges, optionally with line numbers | Usually allow in workspace | Safe |
| `list_files` | Enumerate files by glob or directory | Usually allow in workspace | Safe |
| `search_text` | Search text using ripgrep-style semantics | Usually allow in workspace | Safe |
| `search_symbols` | Query LSP or static index for definitions/references | Usually allow | Safe |
| `write_file` | Create or overwrite a file | Ask or allow by rule | Exclusive |
| `patch_file` | Apply exact text or unified diff patches | Ask or allow by rule | Exclusive |
| `delete_file` | Remove files | Ask; destructive | Exclusive |
| `move_file` | Rename or move files | Ask; destructive when overwrite possible | Exclusive |
| `shell` | Run shell commands | Ask unless read-only and allowlisted | Usually exclusive |
| `read_task_output` | Read background command or agent output | Allow | Safe |
| `stop_task` | Kill a background task | Ask or allow | Exclusive |
| `spawn_agent` | Delegate scoped work to subagent | Ask or policy-dependent | Exclusive at spawn, async after |
| `send_agent_message` | Send follow-up to running subagent | Ask or allow | Exclusive |
| `list_agents` | Inspect running agents and task state | Allow | Safe |
| `update_plan` | Maintain visible plan or todo list | Allow | Exclusive but cheap |
| `ask_user` | Request clarification or approval-like input | Allow, but rate-limit | Exclusive |
| `web_fetch` | Fetch a URL | Domain allowlist or ask | Safe after approval |
| `web_search` | Search the web | Policy-dependent | Safe after approval |
| `structured_output` | Emit machine-readable final data | Allow | Exclusive |

You can implement `git_status`, `git_diff`, `package_test`, and `package_install` as specialized tools or through `shell`. Specialized tools are safer because their inputs are structured and permission checks are easier.

### Optional Model-Facing Tools

| Tool | Add When | Notes |
|---|---|---|
| `notebook_edit` | Supporting notebooks | Needs cell-level diff and output preservation |
| `image_read` | Supporting screenshots or diagrams | Must bound image size and count |
| `open_in_editor` | Interactive desktop workflows | UI-only side effect; ask before launching GUI |
| `mcp_list_resources` | External MCP resources exist | Safe if resource metadata is non-sensitive |
| `mcp_read_resource` | MCP resources are useful context | Permission depends on server trust |
| `tool_search` | Tool count is large | Lets model discover deferred tools without bloating prompt |
| `browser_action` | Browser automation is required | High-risk; sandbox and ask aggressively |
| `remote_run` | Remote development is supported | Requires environment and credential isolation |
| `create_worktree` | Parallel editing is common | Better as internal subagent primitive unless user-facing |
| `secret_lookup` | Enterprise integrations need secrets | Never reveal raw values to the model |

### Internal Runtime Services

| Service | Required Responsibility |
|---|---|
| `ModelProvider` | Provider request serialization, streaming normalization, retries, fallback |
| `ToolRegistry` | Load, filter, order, defer, and lookup tools |
| `PermissionEngine` | Rule matching, mode policy, user prompts, hook decisions |
| `SandboxManager` | Filesystem, process, and network enforcement |
| `ProcessRunner` | Spawn commands, kill process trees, stream output, enforce limits |
| `TaskManager` | Register, update, background, notify, kill, and evict tasks |
| `TranscriptStore` | Append JSONL messages, load sessions, handle tombstones |
| `TaskOutputStore` | Persist large stdout/stderr and agent logs outside memory |
| `ContextManager` | Token estimation, compaction, summarization, large-result replacement |
| `HookRunner` | Execute lifecycle hooks with timeout and abort support |
| `DiffEngine` | Create, render, validate, and apply file diffs |
| `FileSnapshotStore` | Track before/after state for edits and conflict detection |
| `WorktreeManager` | Create, retain, delete, and report isolated worktrees |
| `AgentManager` | Spawn subagents, route messages, track transcripts and permissions |
| `EventBus` | Emit UI, SDK, telemetry, and task lifecycle events |
| `SecretScanner` | Detect accidental secret exposure in logs, diffs, and tool outputs |
| `SettingsStore` | Merge policy, project, user, environment, and session settings |
| `TelemetrySink` | Record timings, decisions, failures, usage, and cost without leaking code |

Settings should be treated as a layered policy cascade. Managed or policy settings are read-only and highest trust; flag/session settings are explicit runtime inputs; project and user settings are editable but lower trust. A plugin-only policy can lock customization surfaces such as hooks, tools, agents, and tool servers to admin-trusted plugin or managed sources.

Plugin loading should validate manifests, namespace contributions, enforce marketplace/source policy, and load optional commands, agents, skills, hooks, tool servers, and settings without requiring engine changes. Tool discovery can defer expensive or rarely used external tools: expose a small search/select tool plus a stable list of deferred names, then return full schemas only when selected.

## 29. High-Level Algorithms

This section gives direct implementation algorithms. Treat these as the skeleton for the harness.

### Bootstrap Algorithm

```text
load environment
load settings from policy, project, user, and CLI
initialize session ID and working directory
load tool registry
load plugins and external tool servers
construct permission context
construct sandbox config
initialize model provider
initialize transcript store
initialize task manager
run session_start hooks
emit ready event
```

Failure handling:

- If settings are invalid, start in safe mode with write and shell tools disabled.
- If plugins fail, keep core tools available and surface plugin errors.
- If sandbox cannot initialize, disable side-effecting tools unless the user explicitly chooses an unsafe mode.

### User Input Algorithm

```text
receive input
normalize text, attachments, pasted files, and images
expand slash commands if enabled
attach selected files or IDE context
run user_prompt_submit hooks
if hook blocks, emit warning and stop
create user message
append to transcript
submit to conversation engine
```

Important distinction: a slash command is local control plane behavior; a normal prompt is model input. Do not blur them.

### Conversation Turn Algorithm

```text
state.messages = transcript tail plus pending input
for turn in 1..maxTurns:
  context = messages after latest compact boundary
  context = replace oversized tool results with persisted references
  context = apply lightweight snips or cached microcompactions
  context = apply committed context collapses
  context = autocompact if token threshold requires it
  normalize context into provider-valid messages

  stream = model.call(context, tools, system_prompt)

  assistant_messages = []
  tool_uses = []
  tool_results = []

  for event in stream:
    if event is recoverable provider error:
      withhold event until recovery is exhausted
    else:
      emit event
    if event is assistant_message:
      assistant_messages.append(event)
      tool_uses.extend(event.tool_uses)
      start_streaming_tools_when_inputs_are_complete(event.tool_uses)
      emit completed streaming tool results when available

  if provider_error:
    recover_or_return_error()

  if tool_uses is empty:
    if recoverable_context_error:
      try collapse drain or reactive compaction, then retry
    if max_output_tokens_error:
      retry with larger output cap, then meta-resume up to a small limit
    if final message is an API error:
      skip stop hooks and return
    run stop hooks; if blocking hook errors exist, append them and retry
    return completed

  consume remaining streaming results or execute remaining tools
  if interrupted:
    synthesize missing tool_results for every unresolved tool_use
    return aborted
  append assistant_messages and tool_results to state.messages
  drain queued task notifications and attachments only after tool_results
  refresh dynamic tool registry
```

The key invariant is that the next provider request must include all assistant tool uses and matching user tool results.

Provider histories must be repaired before every request. Merge compatible adjacent user messages, merge streamed assistant fragments that share a message ID, normalize tool inputs, remove empty assistant blocks, strip provider-incompatible beta fields, drop excess media, remove orphaned tool results, dedupe duplicate tool uses/results, and insert synthetic error results when an assistant tool use lacks a user result. In strict test modes, fail instead of repairing so the bug is visible.

Recoverable provider errors should be withheld from SDK/UI consumers until recovery has either succeeded or definitely failed. This prevents clients from treating an intermediate `prompt too long` or `max output tokens` error as terminal while the engine is still retrying.

If a streaming fallback or model fallback happens after partial assistant output, tombstone the abandoned assistant messages, discard any in-flight streaming tool results for old tool-use IDs, reset the per-attempt tool-use state, and retry with the fallback model. Do not replay provider-specific thinking signatures across incompatible models.

### Tool Call Algorithm

```text
lookup tool by name or alias
if not found:
  return synthetic tool error

parse input with schema
if parse fails:
  return synthetic validation error

run semantic validateInput
if invalid:
  return synthetic validation error

run pre_tool_use hooks
if hook blocks:
  return synthetic blocked error
if hook updates input:
  use updated input

permission = permission_engine.decide(tool, input)
if permission denies:
  return synthetic permission error
if permission asks:
  show prompt or fail closed in headless mode

execute tool with abort signal and progress callback
map output to model-facing result
persist large output if needed
run post_tool_use hooks
return tool result
```

If hooks or permissions need derived fields such as expanded paths, add them on a cloned observable input. Do not mutate the original provider-bound assistant message or the original call input unless a hook explicitly returns an updated input. This preserves replay stability and prompt-cache keys.

Context modifiers returned by tools are safe only when the tool runs serially. If a concurrent-safe tool needs to mutate context, queue and apply those mutations deterministically after the concurrent batch or mark the tool non-concurrent.

### Permission Decision Algorithm

```text
if blanket deny rule matches:
  deny
if blanket ask rule matches and sandbox auto-allow does not apply:
  ask
run tool-specific permission checks
if tool-specific check denies:
  deny
if tool requires human interaction:
  ask
if tool-specific check asks:
  ask
if bypass-resistant safety check rejects:
  ask or deny depending severity
if permission mode is bypass or plan-bypass and the above gates passed:
  allow
if exact allow rule matches:
  allow
if automated classifier enabled:
  allow or deny when high confidence
run permission_request hooks
if hook decides:
  return hook decision
if UI prompt available:
  ask user
else:
  deny
if permission mode is dont_ask and result is ask:
  convert ask to deny
```

Never allow an operation solely because the model argues that it is safe. Safety comes from structured checks.

### File Edit Algorithm

```text
resolve path against workspace
reject path outside allowed roots
reject protected files
read current file snapshot
validate old text or patch applies exactly
produce diff
request permission with diff
if approved:
  write atomically to temp file then rename
  record before/after metadata
  return concise success result
else:
  return rejected tool result
```

If the file changed between read and write, fail with a conflict and tell the model to re-read.

### Shell Execution Algorithm

```text
parse command into semantic segments if possible
classify read-only, write, network, package install, destructive
fail safe if parsing is too complex
resolve cwd and sandbox
request permission
spawn process group with bounded environment
stream stdout/stderr to task output or direct output file
poll output tail for progress
enforce timeout
enforce max output size
on completion:
  flush output
  return bounded result or output-file reference
on interrupt:
  kill or background based on interrupt behavior
```

Shell is the highest-risk tool. Keep its direct API narrow: `command`, `timeout`, `description`, optional `cwd`.

Shell correctness requirements:

- Read-only classification must be parser-backed and command-aware, not a string-prefix heuristic. It must understand `cd`, wrappers, environment prefixes, redirections, compound commands, and allowlisted flags.
- Command permission matching should parse subcommands. For compound commands, a deny or ask rule matching any subcommand should apply to the whole command. If the command is too complex to prove safe, ask or deny.
- Strip only safe wrapper commands and safe environment prefixes when matching allow rules. Deny rules should be harder to bypass and may strip broader environment prefixes, except variables that alter binary resolution or library loading.
- Run shell commands concurrently only when they are proven read-only and concurrency-safe.
- Block long foreground sleeps or idle commands unless explicitly backgrounded. The model should be told to use background execution and a task-output reader.
- Treat tool-internal fields as privileged. If the model supplies an internal-only field, strip it before execution.
- Persist large output to disk with a bounded model-visible preview. Cap persisted output and kill background commands that exceed the cap.
- Preserve enough execution metadata to explain failures: exit code, interruption, timeout, output file path, output size, background task ID, and pre-spawn errors.

### Background Task Algorithm

```text
create task ID
create output file
register task running
detach execution from current turn
on progress:
  update task state
on completion:
  transition status
  enqueue one structured task notification
  schedule output eviction
on kill:
  abort controller
  kill process tree or agent
  transition killed
```

Completion notification should include task ID, output file path, status, and summary. The model can then inspect output explicitly.

If a foreground task is backgrounded after it has already started, flip its existing task state to backgrounded and attach the completion handler there. Re-registering creates duplicate lifecycle events and leaked cleanup callbacks.

For background agents, the initial tool result should return only the task ID, description, prompt, and output path. The full result arrives later as a task notification. Completion, failure, and kill notifications should include any final message, usage summary, and retained worktree location when available.

### Subagent Spawn Algorithm

```text
select agent definition
validate agent exists and is permitted
resolve model and permission mode
resolve tool pool
create agent ID
optionally create isolated worktree
construct child system prompt
construct child initial messages
create child transcript path
create child abort controller
if background:
  register agent task
  run asynchronously
  return task ID
else:
  run child engine to completion
  return concise final result
cleanup agent-local resources
```

Subagents are not magic. They are child conversation engines with scoped tools, scoped permissions, scoped context, and separate transcripts.

Async agent cleanup must clear scoped hooks, scoped tool-server connections, prompt-cache tracking, cloned file-state caches, transcript routing, and per-agent todos. It must also stop any shell or monitor tasks the agent spawned, otherwise subprocesses can outlive their owning agent.

### Resume Algorithm

```text
locate transcript
read bounded JSONL
validate message chain
drop or bridge legacy progress entries
verify every assistant tool_use has matching tool_result
load content replacement records
load task metadata
restore session settings snapshot if available
emit resumed state
```

If the transcript is corrupt, recover the longest valid prefix and report the truncation.

### Interrupt Algorithm

```text
user interrupts
mark current turn abort controller aborted
for each running tool:
  if interruptBehavior is cancel:
    abort and synthesize tool_result
  if interruptBehavior is block:
    wait or offer background
if model stream already emitted tool_use:
  ensure tool_result exists
append interruption message unless a replacement user prompt is queued
return aborted
```

The model API must never see an assistant tool use without a corresponding result after interruption.

## 30. Edge Cases And Corner Cases

### Model And Message Edge Cases

| Scenario | Required Behavior |
|---|---|
| Model emits unknown tool | Return tool error; do not crash |
| Model emits invalid JSON input | Return schema error with expected shape |
| Model emits duplicate tool IDs | Treat as protocol error; synthesize errors and stop turn |
| Model emits tool use then provider stream fails | Emit synthetic result for orphaned tool use before next request |
| Provider fallback after tool calls started | Discard abandoned results and tombstone abandoned assistant messages |
| Provider returns API error instead of assistant text | Surface error; do not run stop hooks |
| Streaming partial tool input never completes | Do not execute; wait for complete block or synthesize cancellation on abort |
| Assistant message contains thinking/signature blocks | Preserve exactly for provider replay; clone only for display |
| Tool result too large | Store output and return preview plus path |
| Final response violates expected JSON schema | Retry with correction or emit structured-output failure |

### Filesystem Edge Cases

| Scenario | Required Behavior |
|---|---|
| Path uses `..` traversal | Resolve then check allowed roots |
| Path is symlink to outside workspace | Check realpath policy before read/write |
| Case-insensitive filesystem collision | Normalize or detect ambiguous paths |
| Unicode equivalent filenames | Avoid normalization surprises; use exact filesystem names |
| Binary file read | Return metadata or bounded binary-safe preview, not raw bytes |
| Very large file | Require offset/range; never load whole file by default |
| File changes after read | Edit fails with conflict; model must re-read |
| File deleted before edit | Return conflict |
| Directory exists where file expected | Return validation error |
| Missing parent directory on write | Either fail or require explicit `create_dirs` flag |
| Newline style differs | Preserve existing style where possible |
| File permissions deny write | Return OS error as tool result |
| Protected settings file requested | Deny even if workspace rule allows |
| Generated/vendor file edit | Ask with warning or deny by policy |

### Shell Edge Cases

| Scenario | Required Behavior |
|---|---|
| Command waits for stdin | Detect stalled prompt and notify model |
| Command produces huge output | Kill or truncate according to output budget |
| Command spawns child processes | Kill process tree on timeout or abort |
| Command daemonizes | Detect parent exit; leave task record if child persists or disallow daemon patterns |
| Command changes cwd internally | Do not mutate harness cwd unless explicit tool exists |
| Cwd deleted before spawn | Return pre-spawn error |
| Timeout fires during permission prompt | Permission prompt should not consume execution timeout |
| Command exits while backgrounding | Avoid duplicate task notification |
| Command uses shell aliases | Prefer non-interactive shell config or explicit shell mode |
| Command includes secrets in env | Redact logs and telemetry |
| Command attempts network | Sandbox or permission layer must handle |
| Package install requested | Ask; classify as network and filesystem write |
| Destructive command requested | Require explicit approval and no broad prefix auto-allow |

### Permission Edge Cases

| Scenario | Required Behavior |
|---|---|
| Allow and deny both match | Deny wins |
| Allow and ask both match | Ask wins unless policy says allow source outranks ask source |
| User denies | Return tool error and continue model loop |
| User approves once | Store session-scoped decision only |
| User approves always | Persist rule only if destination is explicit |
| Headless mode asks | Run hooks or deny; never hang waiting for UI |
| Background agent asks | Bubble to parent if configured, otherwise deny |
| Classifier unavailable | Fail closed or fall back to user prompt |
| Rule pattern is too broad | Reject dangerous broad rules for shell/powershell |
| Tool input modified by hook | Revalidate modified input |
| Permission prompt abandoned | Abort tool and synthesize rejection |

### Subagent Edge Cases

| Scenario | Required Behavior |
|---|---|
| Agent type not found | Return tool error listing available types |
| Agent denied by policy | Return policy denial |
| Agent recursively spawns same delegation pattern | Block recursion or enforce depth limit |
| Parent is interrupted | Sync child aborts; background child survives unless linked |
| Child needs permission in headless mode | Deny or bubble according to config |
| Child edits same file as parent | Prefer worktree isolation; otherwise conflict on write |
| Child inherits stale context | Tell child to re-read before editing |
| Child output is too long | Summarize and persist transcript |
| Child crashes | Mark task failed and notify once |
| Named agent collision | Latest wins only if explicit; otherwise reject duplicate name |

### Context And Compaction Edge Cases

| Scenario | Required Behavior |
|---|---|
| Token estimate is wrong | Keep safety margin and handle provider 413 reactively |
| Compaction omits critical file path | Prefer structured summaries with key files and decisions |
| Compaction occurs with unresolved tool use | Do not compact across unmatched tool-use/result pairs |
| Large result replacement changes on resume | Persist replacement records and reuse them |
| Prompt cache breaks every turn | Stabilize tool order, system prompt, and replacement decisions |
| Stop hook adds too much context | Enforce hook output limits |
| Repeated max-token recovery | Bound retries and surface final error |
| Summary agent fails | Continue without summary; do not block main turn |

### Persistence Edge Cases

| Scenario | Required Behavior |
|---|---|
| JSONL line is corrupt | Load valid prefix and report corruption |
| Transcript is huge | Read head/tail or indexed chain, not entire file |
| Disk full | Stop side effects and report persistence failure |
| Task output file missing | Mark task output unavailable, not task success |
| Process crashes mid-write | Use append-only writes and fsync important metadata |
| Resume after version upgrade | Migrate or tolerate old message shapes |
| Tombstone rewrite too large | Do not rewrite; recover by appending compensating records |
| Duplicate notification after resume | Use task `notified` flag persisted or reconstructed |

### Network And External Tool Edge Cases

| Scenario | Required Behavior |
|---|---|
| Redirect to disallowed host | Re-check final URL |
| Private IP or localhost fetch | Block unless explicitly allowed |
| URL includes credentials | Redact display and logs |
| MCP tool name collides with built-in | Namespace external tools |
| MCP server disconnects mid-call | Return tool error and mark server unhealthy |
| OAuth required | Use explicit auth flow; never ask model for tokens |
| External resource is huge | Bound read and require pagination |
| Tool schema changes mid-session | Version or refresh tools between turns only |
| Deferred tool list changes | Invalidate search caches and refresh available schemas |
| Tool is denied by policy | Filter it before prompt construction, not just at call time |
| Plugin disabled or uninstalled | Prune its hooks/tools immediately or on explicit reload; never leave stale executable hooks |
| Plugin declares sensitive options | Store secrets in secure storage, not general settings |

## 31. What-If Scenarios

Use these scenarios to validate design decisions.

### What If The Model Calls A Write Tool Without Reading First?

The write tool should still validate permissions, but the edit should fail if it depends on unknown current content. For patch-style edits, require exact old text or a current file snapshot. The model should receive a conflict telling it to read the file.

### What If The User Interrupts During A File Write?

Atomic write design matters. Write to a temp file, flush, then rename. If interruption happens before rename, clean temp file. If after rename, report success or verify final file. Never leave a half-written file.

### What If The User Interrupts During A Shell Command?

If the command is foreground and cancellable, kill the process tree and return an interrupted tool result. If the command is long-running but useful, offer or automatically perform backgrounding depending on configuration. Preserve output in a task file.

### What If A Background Task Finishes While The Model Is Thinking?

Do not mutate the in-flight provider request. Queue a structured notification for the next safe insertion point. Abort any speculative response that depends on stale task state.

### What If The Provider Falls Back To A Different Model Mid-Turn?

Discard streamed assistant messages from the abandoned request, tombstone them for UI, and discard any tool results tied to abandoned tool-use IDs. Retry with clean history. If thinking/signature blocks are model-specific, strip or transform them according to provider rules.

### What If The Agent Runs Out Of Context During A Critical Edit?

Do not compact away unresolved edit state. Preserve file paths, before/after snapshots, user approvals, and pending tool-use/result pairs. Compact older discussion first. If still too large, stop and ask the user to narrow scope.

### What If A Subagent Produces A Patch That Conflicts With Parent Changes?

Keep the subagent result isolated. Parent should inspect diff and apply intentionally. If same workspace is used, patch application should fail with conflict and require re-read. Worktree isolation avoids most of this.

### What If A Permission Rule Allows A Dangerous Shell Prefix?

Reject the rule at configuration time or strip it when entering safer modes. Examples include broad shell wildcards, commands that invoke nested shells, download-and-execute patterns, or interpreter one-liners.

### What If A Hook Blocks A Tool But The Model Keeps Retrying?

Return a clear tool error with the hook name and reason. Track repeated denials. After a threshold, inject a meta message telling the model to stop retrying that action and choose a different path.

### What If A Tool Returns Sensitive Data?

Classify output before display, transcript write, and telemetry. Redact known secret patterns. For secret lookup tools, return handles or success flags instead of raw secrets unless the user explicitly requested display.

### What If The Workspace Is Not A Git Repository?

Disable worktree isolation and git-aware tools. File tools and shell can still work with path-based snapshots. The harness should not assume git is present.

### What If Multiple Agents Need To Edit The Same Repository?

Use one worktree per editing agent. Require each agent to commit or summarize changes. Parent integrates results. Never let parallel agents write the same physical checkout unless the user explicitly accepts race risk.

### What If The User Asks For Fully Autonomous Mode?

Autonomy should still be bounded by permission mode, sandbox, budget, and max turns. Fully autonomous does not mean unsandboxed or unaudited. Require explicit scope, time budget, cost budget, and side-effect policy.

## 32. Design Checklists

### Before Exposing A New Tool To The Model

- Define a strict input schema.
- Define a bounded output schema.
- Decide whether it is read-only, destructive, and concurrency-safe.
- Implement semantic validation.
- Implement tool-specific permission checks.
- Implement progress events if it can run longer than one second.
- Implement abort behavior.
- Decide how large results are truncated or persisted.
- Add unit tests for invalid input.
- Add permission tests for allow, ask, and deny.
- Add replay tests if output affects transcript shape.

### Before Adding A New Permission Mode

- Define how it treats reads, writes, shell, network, subagents, and external tools.
- Define whether it can show user prompts.
- Define how it interacts with policy settings.
- Define how it behaves in headless and background contexts.
- Add tests for conflicting allow, ask, and deny rules.
- Add UI labeling so the user can see the active mode.

### Before Supporting A New Model Provider

- Verify streaming event normalization.
- Verify tool-call schema serialization.
- Verify tool-result pairing requirements.
- Verify max token and context limit behavior.
- Verify retryable error classification.
- Verify fallback compatibility.
- Verify whether hidden reasoning or signatures can be replayed.
- Verify prompt caching behavior and cache-break causes.

### Before Shipping Subagents

- Enforce max delegation depth.
- Enforce per-agent tool scope.
- Enforce per-agent permission scope.
- Persist child transcripts.
- Support child abort and kill.
- Support background completion notification.
- Support progress summaries.
- Support worktree isolation for editing agents.
- Test parent interruption and resume.

## 33. Operational Limits

Start with conservative defaults.

| Limit | Suggested Default |
|---|---|
| Max turns per user request | 25 for normal, 100 for explicit autonomous mode |
| Max parallel safe tools | 5 to 10 |
| Max shell timeout | 2 minutes foreground, configurable for background |
| Max inline tool result | 20 KB to 100 KB depending UI |
| Max task output file | 10 MB to 100 MB with hard kill or truncation |
| Max file read | Range-based after 256 KB |
| Max images per request | Small fixed count, such as 10 to 20 |
| Max subagent depth | 1 or 2 |
| Max background agents | 3 to 10 depending machine |
| Max hook runtime | 5 seconds default, 30 seconds hard cap |
| Max transcript raw load | 50 MB unless indexed |

These limits should be visible and configurable, but unsafe increases should require deliberate user action.

## 34. Build-Vs-Buy Decisions

| Component | Build | Buy Or Reuse |
|---|---|---|
| Tool orchestration | Build | Core product behavior |
| Permission engine | Build | Needs product-specific policy |
| Sandbox | Reuse if strong | OS-level enforcement is hard |
| Terminal UI | Reuse framework | Business logic should be UI-independent |
| Diff engine | Reuse library plus custom validation | Avoid weak patch application |
| Process tree kill | Reuse tested package where possible | Platform-specific |
| Token estimation | Reuse provider tokenizer if available | Keep fallback estimator |
| LSP integration | Reuse clients | Protocol is standardized |
| Search | Reuse ripgrep or equivalent | Faster and safer than custom grep |
| Transcript store | Build simple JSONL first | Later add indexes |
| Plugin system | Build minimal manifest loader | Mature marketplace can come later |

## 35. Final Architecture Summary

A complete coding-agent harness has four nested loops:

- **User loop:** accept input, display progress, ask permissions, show results.
- **Model loop:** call model, collect tool requests, return tool results, repeat.
- **Tool loop:** validate, authorize, execute, stream progress, persist output.
- **Task loop:** supervise long-running background work and reinsert completion events.

The strongest design choice is to make all side effects explicit transactions:

```text
intent -> validation -> permission -> sandbox -> execution -> persisted result -> model-visible result
```

If every tool follows that pipeline, the harness remains debuggable as it grows from a read-only assistant into a multi-agent coding system.
