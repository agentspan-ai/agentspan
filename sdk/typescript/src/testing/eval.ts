// ── Eval runner — correctness testing for agent behavior ─────────────
//
// Runs real prompts through agents and evaluates whether the agent's
// behavior matches expectations. Uses structural checks, not LLM judges.

import type { AgentResult } from '../types.js';
import type { Agent } from '../agent.js';
import {
  assertStatus,
  assertNoErrors,
  assertToolUsed,
  assertToolNotUsed,
  assertToolCalledWith,
  assertHandoffTo,
  assertOutputContains,
  assertOutputMatches,
} from './assertions.js';
import { validateStrategy } from './strategy.js';

// ── Types ────────────────────────────────────────────────────────────

export interface EvalCase {
  name: string;
  agent: Agent;
  prompt: string;
  expectTools?: string[];
  expectToolsNotUsed?: string[];
  expectToolArgs?: Record<string, Record<string, unknown>>;
  expectHandoffTo?: string;
  expectNoHandoffTo?: string[];
  expectOutputContains?: string[];
  expectOutputMatches?: string;
  expectStatus?: string;
  expectNoErrors?: boolean;
  validateOrchestration?: boolean;
  customAssertions?: Array<(result: AgentResult) => void>;
  tags?: string[];
}

export interface EvalCheckResult {
  check: string;
  passed: boolean;
  message: string;
}

export interface EvalCaseResult {
  name: string;
  passed: boolean;
  checks: EvalCheckResult[];
  result?: AgentResult;
  error?: string;
  tags: string[];
}

export interface EvalSuiteResult {
  cases: EvalCaseResult[];
  allPassed: boolean;
  passCount: number;
  failCount: number;
  total: number;
  failedCases(): EvalCaseResult[];
  printSummary(): void;
}

export interface Runtime {
  run(agent: Agent, prompt: string): Promise<AgentResult>;
}

// ── Helpers ──────────────────────────────────────────────────────────

function check(
  name: string,
  fn: () => void,
): EvalCheckResult {
  try {
    fn();
    return { check: name, passed: true, message: '' };
  } catch (err) {
    return {
      check: name,
      passed: false,
      message: err instanceof Error ? err.message : String(err),
    };
  }
}

function assertNoHandoff(result: AgentResult, agentName: string): void {
  const handoffs = result.events.filter(
    (ev) => ev.type === 'handoff' && ev.target === agentName,
  );
  if (handoffs.length > 0) {
    throw new Error(
      `Expected NO handoff to '${agentName}', but ${handoffs.length} occurred.`,
    );
  }
}

function makeSuiteResult(cases: EvalCaseResult[]): EvalSuiteResult {
  return {
    cases,
    get allPassed() {
      return cases.every((c) => c.passed);
    },
    get passCount() {
      return cases.filter((c) => c.passed).length;
    },
    get failCount() {
      return cases.filter((c) => !c.passed).length;
    },
    get total() {
      return cases.length;
    },
    failedCases() {
      return cases.filter((c) => !c.passed);
    },
    printSummary() {
      const width = 60;
      console.log(`\n${'='.repeat(width)}`);
      console.log(' Agent Correctness Eval Results');
      console.log(`${'='.repeat(width)}`);

      for (const c of cases) {
        const icon = c.passed ? 'PASS' : 'FAIL';
        console.log(`\n  [${icon}] ${c.name}`);
        if (!c.passed) {
          for (const ch of c.checks) {
            if (!ch.passed) {
              console.log(`         x ${ch.check}: ${ch.message}`);
            }
          }
          if (c.error) {
            console.log(`         x Error: ${c.error}`);
          }
        }
      }

      const passCount = cases.filter((c) => c.passed).length;
      const failCount = cases.filter((c) => !c.passed).length;
      console.log(`\n${'─'.repeat(width)}`);
      console.log(`  ${passCount}/${cases.length} passed, ${failCount} failed`);
      console.log(`${'='.repeat(width)}\n`);
    },
  };
}

// ── CorrectnessEval ──────────────────────────────────────────────────

export class CorrectnessEval {
  private readonly runtime: Runtime;

  constructor(runtime: Runtime) {
    this.runtime = runtime;
  }

  async run(
    cases: EvalCase[],
    opts?: { tags?: string[] },
  ): Promise<EvalSuiteResult> {
    const results: EvalCaseResult[] = [];

    for (const evalCase of cases) {
      if (
        opts?.tags &&
        opts.tags.length > 0 &&
        !(evalCase.tags ?? []).some((t) => opts.tags!.includes(t))
      ) {
        continue;
      }
      const caseResult = await this.runCase(evalCase);
      results.push(caseResult);
    }

    return makeSuiteResult(results);
  }

  private async runCase(evalCase: EvalCase): Promise<EvalCaseResult> {
    const checks: EvalCheckResult[] = [];
    let agentResult: AgentResult | undefined;

    try {
      agentResult = await this.runtime.run(evalCase.agent, evalCase.prompt);
    } catch (err) {
      return {
        name: evalCase.name,
        passed: false,
        checks: [],
        error: `Agent execution failed: ${err}`,
        tags: evalCase.tags ?? [],
      };
    }

    // Status check
    const expectStatus = evalCase.expectStatus ?? 'COMPLETED';
    checks.push(
      check('status', () => assertStatus(agentResult!, expectStatus)),
    );

    // No errors
    if (evalCase.expectNoErrors !== false) {
      checks.push(
        check('no_errors', () => assertNoErrors(agentResult!)),
      );
    }

    // Tool expectations
    if (evalCase.expectTools) {
      for (const toolName of evalCase.expectTools) {
        checks.push(
          check(`tool_used:${toolName}`, () =>
            assertToolUsed(agentResult!, toolName),
          ),
        );
      }
    }

    if (evalCase.expectToolsNotUsed) {
      for (const toolName of evalCase.expectToolsNotUsed) {
        checks.push(
          check(`tool_not_used:${toolName}`, () =>
            assertToolNotUsed(agentResult!, toolName),
          ),
        );
      }
    }

    if (evalCase.expectToolArgs) {
      for (const [toolName, args] of Object.entries(evalCase.expectToolArgs)) {
        checks.push(
          check(`tool_args:${toolName}`, () =>
            assertToolCalledWith(agentResult!, toolName, args),
          ),
        );
      }
    }

    // Handoff expectations
    if (evalCase.expectHandoffTo) {
      checks.push(
        check(`handoff_to:${evalCase.expectHandoffTo}`, () =>
          assertHandoffTo(agentResult!, evalCase.expectHandoffTo!),
        ),
      );
    }

    if (evalCase.expectNoHandoffTo) {
      for (const agentName of evalCase.expectNoHandoffTo) {
        checks.push(
          check(`no_handoff_to:${agentName}`, () =>
            assertNoHandoff(agentResult!, agentName),
          ),
        );
      }
    }

    // Output expectations
    if (evalCase.expectOutputContains) {
      for (const text of evalCase.expectOutputContains) {
        checks.push(
          check(`output_contains:'${text}'`, () =>
            assertOutputContains(agentResult!, text, {
              caseSensitive: false,
            }),
          ),
        );
      }
    }

    if (evalCase.expectOutputMatches) {
      checks.push(
        check(`output_matches:'${evalCase.expectOutputMatches}'`, () =>
          assertOutputMatches(agentResult!, evalCase.expectOutputMatches!),
        ),
      );
    }

    // Strategy validation
    if (evalCase.validateOrchestration !== false) {
      checks.push(
        check('strategy_validation', () =>
          validateStrategy(evalCase.agent, agentResult!),
        ),
      );
    }

    // Custom assertions
    if (evalCase.customAssertions) {
      for (let i = 0; i < evalCase.customAssertions.length; i++) {
        const fn = evalCase.customAssertions[i];
        checks.push(
          check(`custom_${i}`, () => fn(agentResult!)),
        );
      }
    }

    const passed = checks.every((c) => c.passed);
    return {
      name: evalCase.name,
      passed,
      checks,
      result: agentResult,
      tags: evalCase.tags ?? [],
    };
  }
}
