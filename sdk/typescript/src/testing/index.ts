// ── Testing framework for @agentspan-ai/sdk ────────────────

// Mock execution
export { MockEvent, mockRun } from './mock.js';
export type { MockRunOptions } from './mock.js';

// Assertions (17)
export {
  assertToolUsed,
  assertToolNotUsed,
  assertToolCalledWith,
  assertToolCallOrder,
  assertToolsUsedExactly,
  assertOutputContains,
  assertOutputMatches,
  assertOutputType,
  assertStatus,
  assertNoErrors,
  assertEventsContain,
  assertEventSequence,
  assertHandoffTo,
  assertAgentRan,
  assertGuardrailPassed,
  assertGuardrailFailed,
  assertMaxTurns,
} from './assertions.js';

// Fluent API
export { expect, AgentResultExpectation } from './expect.js';

// Strategy validators
export {
  validateStrategy,
  validateSequential,
  validateParallel,
  validateRoundRobin,
  validateRouter,
  validateHandoff,
  validateSwarm,
  validateConstrainedTransitions,
  StrategyViolation,
} from './strategy.js';

// Eval runner
export type {
  EvalCase,
  EvalCheckResult,
  EvalCaseResult,
  EvalSuiteResult,
  Runtime,
} from './eval.js';
export { CorrectnessEval } from './eval.js';

// Record / replay
export { record, replay } from './recording.js';

// Eval case capture
export { evalCaseFromResult, captureEvalCase } from './capture.js';
