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
  GuardrailType,
  TokenUsage,
  ToolContext,
  GuardrailResult,
  GuardrailDef,
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
  TerminationCondition as TerminationConditionInterface,
  HandoffCondition,
  GateCondition,
  CallbackHandler as CallbackHandlerInterface,
  ConversationMemory as ConversationMemoryInterface,
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

// ── Credentials ─────────────────────────────────────────
export {
  extractExecutionToken,
  resolveCredentials,
  getCredential,
  setCredentialContext,
  clearCredentialContext,
  injectCredentials,
} from './credentials.js';

// ── CLI Credential Mapping ──────────────────────────────
export {
  CLI_CREDENTIAL_MAP,
  resolveCliCredentials,
} from './cli-credentials.js';

// ── Guardrails ──────────────────────────────────────────
export type {
  GuardrailOptions,
  ExternalGuardrailOptions,
  RegexGuardrailOptions,
  LLMGuardrailOptions,
  GuardrailDecoratorOptions,
} from './guardrail.js';
export {
  guardrail,
  RegexGuardrail,
  LLMGuardrail,
  Guardrail,
  guardrailsFrom,
} from './guardrail.js';

// ── Memory ──────────────────────────────────────────────
export type { MemoryEntry, MemoryStore, SemanticMemoryOptions } from './memory.js';
export {
  ConversationMemory,
  SemanticMemory,
  InMemoryStore,
} from './memory.js';

// ── Termination ─────────────────────────────────────────
export {
  TerminationCondition,
  TextMention,
  StopMessage,
  MaxMessage,
  TokenUsageCondition,
  AndCondition,
  OrCondition,
} from './termination.js';
export type { TerminationContext, TerminationResult } from './termination.js';

// ── Handoffs ────────────────────────────────────────────
export type { HandoffContext } from './handoff.js';
export {
  OnToolResult,
  OnTextMention,
  OnCondition,
  TextGate,
  gate,
} from './handoff.js';

// ── Callbacks ───────────────────────────────────────────
export {
  CallbackHandler,
  CALLBACK_POSITIONS,
  getCallbackWorkerNames,
} from './callback.js';

// ── Code Execution ──────────────────────────────────────
export type { ExecutionResult } from './code-execution.js';
export {
  CommandValidator,
  CodeExecutor,
  LocalCodeExecutor,
  DockerCodeExecutor,
  JupyterCodeExecutor,
  ServerlessCodeExecutor,
} from './code-execution.js';

// ── Claude Code ─────────────────────────────────────────
export { ClaudeCode, PermissionMode, resolveClaudeCodeModel } from './claude-code.js';

// ── CLI Config ──────────────────────────────────────────
export type { CliConfigOptions } from './cli-config.js';
export { makeCliTool } from './cli-config.js';

// ── Extended Agent Types ────────────────────────────────
export type { UserProxyMode, UserProxyAgentOptions, GPTAssistantAgentOptions } from './ext.js';
export { UserProxyAgent, GPTAssistantAgent } from './ext.js';

// ── Discovery ───────────────────────────────────────────
export { discoverAgents } from './discovery.js';

// ── Tracing ─────────────────────────────────────────────
export { isTracingEnabled } from './tracing.js';

// ── Skills ───────────────────────────────────────────────
export type { SkillOptions, LoadSkillsOptions, SkillWorker } from './skill.js';
export {
  skill,
  loadSkills,
  SkillLoadError,
  formatSkillParams,
  formatPromptWithParams,
  createSkillWorkers,
} from './skill.js';

// ── Framework Integration ───────────────────────────────
export { detectFramework } from './frameworks/detect.js';
export type { WorkerInfo } from './frameworks/serializer.js';
export { serializeFrameworkAgent } from './frameworks/serializer.js';
export { serializeLangGraph } from './frameworks/langgraph-serializer.js';
export { serializeLangChain } from './frameworks/langchain-serializer.js';
