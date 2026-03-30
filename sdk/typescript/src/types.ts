// ── String union types ────────────────────────────────────

/**
 * Multi-agent orchestration strategy.
 */
export type Strategy =
  | 'handoff'
  | 'sequential'
  | 'parallel'
  | 'router'
  | 'round_robin'
  | 'random'
  | 'swarm'
  | 'manual';

/**
 * Agent event types emitted during execution.
 */
export type EventType =
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'guardrail_pass'
  | 'guardrail_fail'
  | 'waiting'
  | 'handoff'
  | 'message'
  | 'error'
  | 'done';

/**
 * Terminal workflow status.
 */
export type Status = 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'TIMED_OUT';

/**
 * Reason the agent finished execution.
 */
export type FinishReason =
  | 'stop'
  | 'length'
  | 'tool_calls'
  | 'error'
  | 'cancelled'
  | 'timeout'
  | 'guardrail'
  | 'rejected';

/**
 * Guardrail failure handling strategy.
 */
export type OnFail = 'retry' | 'raise' | 'fix' | 'human';

/**
 * Guardrail position — applied to input or output.
 */
export type Position = 'input' | 'output';

/**
 * Guardrail type determining execution strategy.
 */
export type GuardrailType = 'regex' | 'llm' | 'custom' | 'external';

/**
 * Complete guardrail definition for serialization and worker registration.
 */
export interface GuardrailDef {
  name: string;
  position: Position;
  onFail: OnFail;
  guardrailType: GuardrailType;
  maxRetries?: number;
  taskName?: string;
  /** Local handler function, for custom guardrails only. */
  func?: ((content: string) => GuardrailResult | Promise<GuardrailResult>) | null;
  // Regex guardrail fields
  patterns?: string[];
  mode?: 'block' | 'allow';
  message?: string;
  // LLM guardrail fields
  model?: string;
  policy?: string;
  maxTokens?: number;
}

/**
 * Tool execution type determining where/how the tool runs.
 */
export type ToolType =
  | 'worker'
  | 'http'
  | 'api'
  | 'mcp'
  | 'agent_tool'
  | 'human'
  | 'generate_image'
  | 'generate_audio'
  | 'generate_video'
  | 'generate_pdf'
  | 'rag_search'
  | 'rag_index';

/**
 * Supported framework identifiers for auto-detection.
 */
export type FrameworkId =
  | 'langgraph'
  | 'langchain'
  | 'openai'
  | 'google_adk';

// ── Data interfaces ──────────────────────────────────────

/**
 * Token usage statistics for an LLM call.
 */
export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

/**
 * Execution context passed to tool functions.
 * `state` is mutable — mutations are captured as `_state_updates`.
 */
export interface ToolContext {
  sessionId: string;
  executionId: string;
  agentName: string;
  metadata: Record<string, unknown>;
  dependencies: Record<string, unknown>;
  /** Mutable state object. Mutations are captured and sent as _state_updates. */
  state: Record<string, unknown>;
}

/**
 * Result returned by a guardrail function.
 */
export interface GuardrailResult {
  passed: boolean;
  message?: string;
  fixedOutput?: string;
}

/**
 * A single event emitted during agent execution.
 */
export interface AgentEvent {
  /** Event type — standard EventType or server-only passthrough. */
  type: EventType | string;
  content?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  target?: string;
  output?: unknown;
  executionId?: string;
  guardrailName?: string;
  timestamp?: number;
}

/**
 * Live status of a running agent workflow.
 */
export interface AgentStatus {
  executionId: string;
  isComplete: boolean;
  isRunning: boolean;
  isWaiting: boolean;
  output?: unknown;
  status: string;
  reason?: string;
  currentTask?: string;
  messages: unknown[];
  pendingTool?: { name: string; args: Record<string, unknown> };
}

/**
 * Information returned after deploying an agent workflow.
 */
export interface DeploymentInfo {
  executionId: string;
  agentName: string;
  /** Included in deploy() response — the compiled workflow definition. */
  workflowDef?: object;
}

/**
 * Named prompt template with optional variable substitution.
 */
export interface PromptTemplate {
  name: string;
  variables?: Record<string, string>;
  version?: number;
}

/**
 * Credential file reference for tool/agent credential injection.
 */
export interface CredentialFile {
  envVar: string;
  relativePath?: string;
  content?: string;
}

/**
 * Agent-level code execution configuration.
 */
export interface CodeExecutionConfig {
  enabled: boolean;
  allowedLanguages?: string[];
  allowedCommands?: string[];
  timeout?: number;
}

/**
 * Agent-level CLI tool configuration.
 */
export interface CliConfig {
  enabled: boolean;
  allowedCommands?: string[];
  timeout?: number;
  allowShell?: boolean;
}

/**
 * Options for run/start/stream execution calls.
 */
export interface RunOptions {
  sessionId?: string;
  media?: string[];
  idempotencyKey?: string;
  timeoutSeconds?: number;
  credentials?: string[];
  /** AbortSignal for cancellation/timeout. */
  signal?: AbortSignal;
}

// ── Tool definition ──────────────────────────────────────

/**
 * Complete tool definition for serialization and worker registration.
 */
export interface ToolDef {
  name: string;
  description: string;
  /** JSON Schema object describing the tool's input parameters. */
  inputSchema: object;
  /** Optional JSON Schema for tool output. */
  outputSchema?: object;
  toolType: ToolType;
  /** Local handler function, or null for server-side/external tools. */
  func?: Function | null;
  approvalRequired?: boolean;
  timeoutSeconds?: number;
  external?: boolean;
  isolated?: boolean;
  credentials?: (string | CredentialFile)[];
  guardrails?: unknown[];
  config?: Record<string, unknown>;
}

// ── Agent result ─────────────────────────────────────────

/**
 * Result of an agent execution.
 *
 * `output` is always a Record — primitives are wrapped per normalization rules:
 * - string -> { result: string }
 * - null/undefined + COMPLETED -> { result: null }
 * - null/undefined + FAILED -> { error: errorMessage }
 * - object -> used as-is
 */
export interface AgentResult {
  output: Record<string, unknown>;
  executionId: string;
  correlationId?: string;
  messages: unknown[];
  toolCalls: unknown[];
  status: Status;
  finishReason: FinishReason;
  error?: string;
  tokenUsage?: TokenUsage;
  metadata?: Record<string, unknown>;
  events: AgentEvent[];
  subResults?: Record<string, unknown>;
  readonly isSuccess: boolean;
  readonly isFailed: boolean;
  readonly isRejected: boolean;
  printResult(): void;
}

/**
 * Create a concrete AgentResult object with computed properties.
 */
export function createAgentResult(data: {
  output: Record<string, unknown>;
  executionId: string;
  correlationId?: string;
  messages?: unknown[];
  toolCalls?: unknown[];
  status: Status;
  finishReason: FinishReason;
  error?: string;
  tokenUsage?: TokenUsage;
  metadata?: Record<string, unknown>;
  events?: AgentEvent[];
  subResults?: Record<string, unknown>;
}): AgentResult {
  const result: AgentResult = {
    output: data.output,
    executionId: data.executionId,
    correlationId: data.correlationId,
    messages: data.messages ?? [],
    toolCalls: data.toolCalls ?? [],
    status: data.status,
    finishReason: data.finishReason,
    error: data.error,
    tokenUsage: data.tokenUsage,
    metadata: data.metadata,
    events: data.events ?? [],
    subResults: data.subResults,

    get isSuccess(): boolean {
      return data.status === 'COMPLETED';
    },

    get isFailed(): boolean {
      return data.status === 'FAILED' || data.status === 'TIMED_OUT';
    },

    get isRejected(): boolean {
      return data.finishReason === 'rejected';
    },

    printResult(): void {
      const statusIcon = result.isSuccess ? '[OK]' : '[FAIL]';
      console.log(`${statusIcon} Agent Result (${result.executionId})`);
      console.log(`  Status: ${result.status}`);
      console.log(`  Finish Reason: ${result.finishReason}`);
      if (result.error) {
        console.log(`  Error: ${result.error}`);
      }
      console.log(`  Output:`, JSON.stringify(result.output, null, 2));
      if (result.tokenUsage) {
        console.log(
          `  Tokens: ${result.tokenUsage.promptTokens} prompt + ${result.tokenUsage.completionTokens} completion = ${result.tokenUsage.totalTokens} total`,
        );
      }
      console.log(`  Events: ${result.events.length}`);
      console.log(`  Tool Calls: ${result.toolCalls.length}`);
      console.log(`  Messages: ${result.messages.length}`);
    },
  };

  return result;
}

/**
 * Normalize raw server output into a Record<string, unknown>.
 *
 * Rules:
 * 1. string -> { result: string }
 * 2. null/undefined + COMPLETED -> { result: null }
 * 3. null/undefined + FAILED -> { error: errorMessage }
 * 4. object -> as-is
 * 5. Always Record<string, unknown>
 */
export function normalizeOutput(
  raw: unknown,
  status: Status,
  errorMessage?: string,
): Record<string, unknown> {
  if (typeof raw === 'string') {
    return { result: raw };
  }
  if (raw == null) {
    if (status === 'COMPLETED') {
      return { result: null };
    }
    return { error: errorMessage ?? 'Unknown error' };
  }
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  // For arrays or other non-object types, wrap
  return { result: raw };
}

/**
 * Strip internal Conductor routing keys from event args.
 * Removes `_agent_state` and `method` keys.
 */
export function stripInternalEventKeys(event: AgentEvent): AgentEvent {
  if (!event.args) return event;
  const cleaned = { ...event.args };
  delete cleaned['_agent_state'];
  delete cleaned['method'];
  return { ...event, args: cleaned };
}
