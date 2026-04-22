/**
 * Suite 19: Token Usage — validates token usage collection and aggregation.
 *
 * Ported from Python: tests/integration/test_token_usage.py
 *
 * Tests:
 *   - Single agent: tokenUsage is populated with plausible values
 *   - Sequential pipeline (researcher >> writer): tokens aggregated across sub-workflows
 *   - Parallel agents (pros + cons): tokens aggregated across parallel sub-workflows
 *
 * All validation is algorithmic — no LLM output parsing.
 * No mocks — all tests are real end-to-end.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime } from '@agentspan-ai/sdk';
import type { TokenUsage } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL, TIMEOUT, runDiagnostic } from './helpers';

let runtime: AgentRuntime;

// ── Helpers ─────────────────────────────────────────────────────────────

/**
 * Assert that a TokenUsage object has plausible values.
 * Key algorithmic assertion: total = prompt + completion.
 */
function assertUsage(usage: TokenUsage | undefined, label: string): void {
  expect(usage, `${label}: tokenUsage should exist`).toBeDefined();
  expect(usage!.promptTokens, `${label}: promptTokens > 0`).toBeGreaterThan(0);
  expect(usage!.completionTokens, `${label}: completionTokens > 0`).toBeGreaterThan(0);
  expect(usage!.totalTokens, `${label}: totalTokens > 0`).toBeGreaterThan(0);
  // Algorithmic: total must equal prompt + completion
  expect(usage!.totalTokens, `${label}: total = prompt + completion`).toBe(
    usage!.promptTokens + usage!.completionTokens,
  );
}

// ── Tests ───────────────────────────────────────────────────────────────

describe('Suite 19: Token Usage', { timeout: 600_000 }, () => {
  beforeAll(async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();
  });

  afterAll(() => runtime.shutdown());

  // ── Single agent ────────────────────────────────────────────────────

  it('single agent tokens populated', async () => {
    const agent = new Agent({
      name: 'e2e_ts_token_single',
      model: MODEL,
      instructions: 'Answer in one sentence.',
    });

    const result = await runtime.run(agent, 'What is 2+2?', { timeout: TIMEOUT });

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.status, `[Single token] ${diag}`).toBe('COMPLETED');
    assertUsage(result.tokenUsage, 'single agent');
  });

  // ── Sequential pipeline ─────────────────────────────────────────────

  it('sequential tokens aggregated', async () => {
    const researcher = new Agent({
      name: 'e2e_ts_tok_researcher',
      model: MODEL,
      instructions: 'List 2 key facts about the topic. Be brief.',
    });
    const writer = new Agent({
      name: 'e2e_ts_tok_writer',
      model: MODEL,
      instructions: 'Write one sentence summarising the provided facts.',
    });
    const pipeline = researcher.pipe(writer);

    const result = await runtime.run(
      pipeline,
      'The benefits of electric vehicles',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.status, `[Sequential token] ${diag}`).toBe('COMPLETED');
    assertUsage(result.tokenUsage, 'sequential pipeline');

    // Two LLM calls must produce more tokens than a typical single call.
    // 20 tokens is a very conservative lower bound.
    expect(
      result.tokenUsage!.totalTokens,
      `Expected >= 20 total tokens for a two-stage pipeline, got ${result.tokenUsage!.totalTokens}`,
    ).toBeGreaterThanOrEqual(20);
  });

  // ── Parallel agents ─────────────────────────────────────────────────

  it('parallel tokens aggregated', async () => {
    const prosAnalyst = new Agent({
      name: 'e2e_ts_tok_pros',
      model: MODEL,
      instructions: 'List one pro. One sentence.',
    });
    const consAnalyst = new Agent({
      name: 'e2e_ts_tok_cons',
      model: MODEL,
      instructions: 'List one con. One sentence.',
    });
    const team = new Agent({
      name: 'e2e_ts_tok_parallel',
      model: MODEL,
      agents: [prosAnalyst, consAnalyst],
      strategy: 'parallel',
    });

    const result = await runtime.run(
      team,
      'Evaluate investing in AI.',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.status, `[Parallel token] ${diag}`).toBe('COMPLETED');
    assertUsage(result.tokenUsage, 'parallel agents');

    // Multiple LLM calls (coordinator + 2 sub-agents) must produce more tokens
    // than a single call. 20 tokens is a very conservative lower bound.
    expect(
      result.tokenUsage!.totalTokens,
      `Expected >= 20 total tokens for parallel agents, got ${result.tokenUsage!.totalTokens}`,
    ).toBeGreaterThanOrEqual(20);
  });
});
