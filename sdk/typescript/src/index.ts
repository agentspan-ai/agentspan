// ── Types ────────────────────────────────────────────────
export type {
  Strategy,
  EventType,
  Status,
  FinishReason,
  OnFail,
  Position,
  ToolType,
  FrameworkId,
  TokenUsage,
  ToolContext,
  GuardrailResult,
  AgentEvent,
  AgentStatus,
  DeploymentInfo,
  PromptTemplate as PromptTemplateInterface,
  CredentialFile,
  CodeExecutionConfig,
  CliConfig,
  RunOptions,
  ToolDef,
  AgentResult,
} from './types.js';

export {
  createAgentResult,
  normalizeOutput,
  stripInternalEventKeys,
} from './types.js';

// ── Errors ───────────────────────────────────────────────
export {
  AgentspanError,
  AgentAPIError,
  AgentNotFoundError,
  ConfigurationError,
  CredentialNotFoundError,
  CredentialAuthError,
  CredentialRateLimitError,
  CredentialServiceError,
  SSETimeoutError,
  GuardrailFailedError,
} from './errors.js';

// ── Config ───────────────────────────────────────────────
export type { AgentConfigOptions, LogLevel } from './config.js';
export { AgentConfig, normalizeServerUrl } from './config.js';

// ── Tool System ─────────────────────────────────────────
export type { ToolFunction, ToolOptions } from './tool.js';
export type {
  HttpToolOptions,
  McpToolOptions,
  ApiToolOptions,
  AgentToolOptions,
  HumanToolOptions,
  ImageToolOptions,
  AudioToolOptions,
  VideoToolOptions,
  PdfToolOptions,
  SearchToolOptions,
  IndexToolOptions,
} from './tool.js';
export {
  tool,
  getToolDef,
  normalizeToolInput,
  isZodSchema,
  httpTool,
  mcpTool,
  apiTool,
  agentTool,
  humanTool,
  imageTool,
  audioTool,
  videoTool,
  pdfTool,
  searchTool,
  indexTool,
  Tool,
  toolsFrom,
} from './tool.js';

// ── Agent ───────────────────────────────────────────────
export type {
  AgentOptions,
  ScatterGatherOptions,
  TerminationCondition,
  HandoffCondition,
  GateCondition,
  CallbackHandler,
  ConversationMemory,
} from './agent.js';
export {
  Agent,
  PromptTemplate,
  scatterGather,
  AgentDec,
  agentsFrom,
  agent,
} from './agent.js';

// ── Serializer ──────────────────────────────────────────
export type { SerializeOptions } from './serializer.js';
export { AgentConfigSerializer } from './serializer.js';

// ── Worker Manager ──────────────────────────────────────
export type { WorkerHandler } from './worker.js';
export {
  WorkerManager,
  coerceValue,
  extractToolContext,
  captureStateMutations,
  appendStateUpdates,
  stripInternalKeys,
  recordFailure,
  recordSuccess,
  isCircuitBreakerOpen,
  resetCircuitBreaker,
  resetAllCircuitBreakers,
} from './worker.js';

// ── Result ──────────────────────────────────────────────
export type { MakeAgentResultData } from './result.js';
export {
  makeAgentResult,
  EventTypes,
  Statuses,
  FinishReasons,
  TERMINAL_STATUSES,
} from './result.js';

// ── Stream ──────────────────────────────────────────────
export type { RespondFn } from './stream.js';
export { AgentStream } from './stream.js';

// ── Runtime ─────────────────────────────────────────────
export type { AgentHandle } from './runtime.js';
export {
  AgentRuntime,
  configure,
  run,
  start,
  stream,
  deploy,
  plan,
  serve,
  shutdown,
} from './runtime.js';
