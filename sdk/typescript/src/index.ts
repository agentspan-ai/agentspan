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
  PendingTool,
  PendingToolCall,
  DeploymentInfo,
  PromptTemplate as PromptTemplateInterface,
  CodeExecutionConfig,
  CliConfig,
  RunOptions,
  ToolDef,
  PrefillToolCall,
  AgentResult,
} from "./types.js";

export { createAgentResult, normalizeOutput, stripInternalEventKeys } from "./types.js";

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
  TerminalToolError,
  GuardrailFailedError,
} from "./errors.js";

// ── Config ───────────────────────────────────────────────
export type { AgentConfigOptions, LogLevel } from "./config.js";
export { AgentConfig, normalizeServerUrl } from "./config.js";

// ── Tool System ─────────────────────────────────────────
export type { ToolFunction, ToolOptions } from "./tool.js";
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
  WaitForMessageToolOptions,
} from "./tool.js";
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
  waitForMessageTool,
  Tool,
  toolsFrom,
} from "./tool.js";

// ── Agent ───────────────────────────────────────────────
export type {
  AgentOptions,
  ScatterGatherOptions,
  TerminationCondition as TerminationConditionInterface,
  HandoffCondition,
  GateCondition,
  CallbackHandler as CallbackHandlerInterface,
  ConversationMemory as ConversationMemoryInterface,
} from "./agent.js";
export { Agent, PromptTemplate, scatterGather, AgentDec, agentsFrom, agent } from "./agent.js";

// ── Serializer ──────────────────────────────────────────
export type { SerializeOptions } from "./serializer.js";
export { AgentConfigSerializer } from "./serializer.js";

// ── Worker Manager ──────────────────────────────────────
export type { WorkerHandler } from "./worker.js";
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
} from "./worker.js";

// ── Result ──────────────────────────────────────────────
export type { MakeAgentResultData } from "./result.js";
export {
  makeAgentResult,
  EventTypes,
  Statuses,
  FinishReasons,
  TERMINAL_STATUSES,
} from "./result.js";

// ── Stream ──────────────────────────────────────────────
export type { RespondFn } from "./stream.js";
export { AgentStream } from "./stream.js";

// ── Runtime ─────────────────────────────────────────────
export type { AgentHandle } from "./runtime.js";
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
} from "./runtime.js";

// ── Control-plane / Workflow clients ────────────────────
export type { ClientHandle } from "./agent-client.js";
export { AgentClient, decodeJwtExp } from "./agent-client.js";
export type { WorkflowExecution, WorkflowTokenUsage } from "./workflow-client.js";
export { WorkflowClient } from "./workflow-client.js";

// ── Scheduling ──────────────────────────────────────────
export {
  Schedule,
  ScheduleClient,
  ScheduleError,
  ScheduleNameConflict,
  ScheduleNotFound,
  InvalidCronExpression,
} from "./schedule.js";
export type { ScheduleOptions, ScheduleInfo, SchedulerFetcher } from "./schedule.js";
import * as schedules from "./schedules-api.js";
export { schedules };

// ── Credentials ─────────────────────────────────────────
export {
  extractExecutionToken,
  resolveCredentials,
  getCredential,
  setCredentialContext,
  runWithCredentialContext,
  clearCredentialContext,
} from "./credentials.js";

// ── Guardrails ──────────────────────────────────────────
export type {
  GuardrailOptions,
  ExternalGuardrailOptions,
  RegexGuardrailOptions,
  LLMGuardrailOptions,
  GuardrailDecoratorOptions,
} from "./guardrail.js";
export { guardrail, RegexGuardrail, LLMGuardrail, Guardrail, guardrailsFrom } from "./guardrail.js";

// ── Memory ──────────────────────────────────────────────
export type { MemoryEntry, MemoryStore, SemanticMemoryOptions } from "./memory.js";
export { ConversationMemory, SemanticMemory, InMemoryStore } from "./memory.js";

// ── Plans (Strategy.PLAN_EXECUTE typed builders) ────────
export type {
  GenerateOptions,
  OpOptions,
  StepOptions,
  ValidationOptions,
  ActionOptions,
  PlanOptions,
  PlanLike,
} from "./plans.js";
export {
  Plan,
  Step,
  Op,
  Generate,
  Validation,
  Action,
  Ref,
  Context,
  coercePlan,
  serializePlanValue,
} from "./plans.js";

// ── Termination ─────────────────────────────────────────
export {
  TerminationCondition,
  TextMention,
  StopMessage,
  MaxMessage,
  TokenUsageCondition,
  AndCondition,
  OrCondition,
} from "./termination.js";
export type { TerminationContext, TerminationResult } from "./termination.js";

// ── Handoffs ────────────────────────────────────────────
export type { HandoffContext } from "./handoff.js";
export { OnToolResult, OnTextMention, OnCondition, TextGate, gate } from "./handoff.js";

// ── Callbacks ───────────────────────────────────────────
export { CallbackHandler, CALLBACK_POSITIONS, getCallbackWorkerNames } from "./callback.js";

// ── Code Execution ──────────────────────────────────────
export type { ExecutionResult } from "./code-execution.js";
export {
  CommandValidator,
  CodeExecutor,
  LocalCodeExecutor,
  DockerCodeExecutor,
  JupyterCodeExecutor,
  ServerlessCodeExecutor,
} from "./code-execution.js";

// ── Claude Code ─────────────────────────────────────────
export { ClaudeCode, PermissionMode, resolveClaudeCodeModel } from "./claude-code.js";

// ── CLI Config ──────────────────────────────────────────
export type { CliConfigOptions } from "./cli-config.js";
export { makeCliTool } from "./cli-config.js";

// ── Extended Agent Types ────────────────────────────────
export type { GPTAssistantAgentOptions } from "./ext.js";
export { GPTAssistantAgent } from "./ext.js";

// ── Discovery ───────────────────────────────────────────
export { discoverAgents } from "./discovery.js";

// ── Tracing ─────────────────────────────────────────────
export { isTracingEnabled } from "./tracing.js";

// ── Skills ───────────────────────────────────────────────
export type { SkillOptions, LoadSkillsOptions, SkillWorker } from "./skill.js";
export {
  skill,
  loadSkills,
  SkillLoadError,
  formatSkillParams,
  formatPromptWithParams,
  createSkillWorkers,
} from "./skill.js";

// ── Framework Integration ───────────────────────────────
export { detectFramework } from "./frameworks/detect.js";
export type { WorkerInfo } from "./frameworks/serializer.js";
export { serializeFrameworkAgent } from "./frameworks/serializer.js";
export { serializeLangGraph } from "./frameworks/langgraph-serializer.js";
export { serializeLangChain } from "./frameworks/langchain-serializer.js";
