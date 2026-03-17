/**
 * TypeScript type definitions for @agentspan/sdk (JavaScript package).
 */

// ── Config ────────────────────────────────────────────────────────────────

export interface AgentConfigOptions {
  serverUrl?: string;
  authKey?: string;
  authSecret?: string;
  workerPollIntervalMs?: number;
  logLevel?: string;
}

export declare class AgentConfig {
  readonly serverUrl: string;
  readonly authKey: string | undefined;
  readonly authSecret: string | undefined;
  readonly workerPollIntervalMs: number;
  readonly logLevel: string;
  constructor(options?: AgentConfigOptions);
  static fromEnv(): AgentConfig;
}

// ── Tool ─────────────────────────────────────────────────────────────────

export interface JsonSchema {
  type: string;
  properties?: Record<string, JsonSchema & { description?: string }>;
  required?: string[];
  description?: string;
  [key: string]: unknown;
}

export interface ToolOptions {
  name?: string;
  description: string;
  inputSchema: JsonSchema;
  outputSchema?: JsonSchema;
  approvalRequired?: boolean;
  timeoutSeconds?: number;
}

export interface ToolDef {
  name: string;
  description: string;
  inputSchema: JsonSchema;
  outputSchema?: JsonSchema;
  func: ((...args: unknown[]) => unknown) | null;
  approvalRequired: boolean;
  timeoutSeconds?: number | null;
  toolType: string;
  config: Record<string, unknown>;
}

export type ToolFunction<TInput = Record<string, unknown>, TOutput = unknown> = {
  (input: TInput): Promise<TOutput>;
  _toolDef: ToolDef;
};

export declare function tool<TInput = Record<string, unknown>, TOutput = unknown>(
  fn: (input: TInput) => Promise<TOutput> | TOutput,
  options: ToolOptions
): ToolFunction<TInput, TOutput>;

export declare function getToolDef(toolObj: unknown): ToolDef;

export interface HttpToolOptions {
  name: string;
  description: string;
  url: string;
  method?: string;
  headers?: Record<string, string>;
  inputSchema?: JsonSchema;
  accept?: string[];
  contentType?: string;
}

export declare function httpTool(options: HttpToolOptions): ToolDef;

export interface McpToolOptions {
  name: string;
  description: string;
  serverUrl: string;
  headers?: Record<string, string>;
  inputSchema?: JsonSchema;
}

export declare function mcpTool(options: McpToolOptions): ToolDef;

// ── Agent ─────────────────────────────────────────────────────────────────

export type Strategy =
  | 'handoff'
  | 'sequential'
  | 'parallel'
  | 'router'
  | 'round_robin'
  | 'random'
  | 'swarm'
  | 'manual';

export interface AgentOptions {
  name: string;
  model?: string;
  instructions?: string | (() => string);
  tools?: Array<ToolFunction<any, any> | ToolDef>;
  agents?: Agent[];
  strategy?: Strategy;
  router?: Agent | null;
  maxTurns?: number;
  maxTokens?: number;
  temperature?: number;
  timeoutSeconds?: number;
  external?: boolean;
  metadata?: Record<string, unknown>;
}

export declare class Agent {
  readonly name: string;
  readonly model: string;
  readonly instructions: string | (() => string) | null;
  readonly tools: Array<ToolFunction<any, any> | ToolDef>;
  readonly agents: Agent[];
  readonly strategy: Strategy | null;
  readonly maxTurns: number;
  readonly maxTokens: number | null;
  readonly temperature: number | null;
  readonly timeoutSeconds: number | null;
  readonly external: boolean;
  readonly metadata: Record<string, unknown>;
  constructor(options: AgentOptions);
}

// ── Result ────────────────────────────────────────────────────────────────

export type Status = 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'TIMED_OUT';

export type FinishReason =
  | 'stop' | 'LENGTH' | 'tool_calls' | 'error'
  | 'cancelled' | 'timeout' | 'guardrail' | 'rejected';

export interface TokenUsage {
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface AgentResult {
  workflowId: string;
  output: Record<string, unknown> | null;
  status: Status;
  messages: Array<Record<string, unknown>>;
  toolCalls: Array<Record<string, unknown>>;
  finishReason?: FinishReason;
  error?: string;
  tokenUsage?: TokenUsage;
  subResults: Record<string, unknown>;
  readonly isSuccess: boolean;
  readonly isFailed: boolean;
  printResult(): void;
}

export interface AgentStatus {
  workflowId: string;
  isComplete: boolean;
  isRunning: boolean;
  isWaiting: boolean;
  output: Record<string, unknown> | null;
  status: string;
  reason?: string;
  currentTask?: string;
  messages: Array<Record<string, unknown>>;
}

export interface AgentHandle {
  workflowId: string;
  getStatus(): Promise<AgentStatus>;
  wait(pollIntervalMs?: number): Promise<AgentResult>;
  approve(output?: Record<string, unknown>): Promise<void>;
  reject(reason?: string): Promise<void>;
}

export type EventType =
  | 'thinking' | 'tool_call' | 'tool_result'
  | 'guardrail_pass' | 'guardrail_fail'
  | 'waiting' | 'error' | 'done';

export interface AgentEvent {
  type: EventType;
  content?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  output?: Record<string, unknown> | null;
  error?: string;
  raw?: Record<string, unknown>;
}

export declare const EventType: Record<string, string>;
export declare const Status: Record<string, string>;
export declare const FinishReason: Record<string, string>;

// ── Runtime ───────────────────────────────────────────────────────────────

export interface RunOptions {
  sessionId?: string;
  timeoutSeconds?: number;
}

export declare class AgentRuntime {
  constructor(options?: AgentConfigOptions | AgentConfig);
  run(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentResult>;
  start(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentHandle>;
  stream(agent: Agent, prompt: string, options?: RunOptions): AsyncIterable<AgentEvent>;
  plan(agent: Agent): Promise<Record<string, unknown>>;
  shutdown(): Promise<void>;
}
