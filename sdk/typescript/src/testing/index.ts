// ── Testing framework for @agentspan-ai/sdk ────────────────

// Mock execution
export type { MockRunOptions } from './mock.js';
export { mockRun } from './mock.js';

// Fluent assertions
export type { ResultExpectation } from './expect.js';
export { expectResult } from './expect.js';

// Individual assertion functions
export {
  assertToolUsed,
  assertGuardrailPassed,
  assertAgentRan,
  assertHandoffTo,
  assertStatus,
  assertNoErrors,
} from './assertions.js';

// LLM-based evaluation
export type {
  EvalResult,
  Rubric,
  EvaluateOptions,
  CorrectnessEvalOptions,
} from './eval.js';
export { CorrectnessEval } from './eval.js';

// Strategy validation
export { validateStrategy } from './strategy.js';

// Record / replay
export type { RecordingFixture, RecordOptions } from './recording.js';
export { record, replay } from './recording.js';
