// ── Fluent assertion API for agent results ───────────────────────────
//
// Provides a chainable interface wrapping the assertion functions.
//
// Usage:
//   expect(result).completed().usedTool('search').outputContains('answer');

import type { AgentResult } from '../types.js';
import {
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

export class AgentResultExpectation {
  private readonly result: AgentResult;

  constructor(result: AgentResult) {
    this.result = result;
  }

  // ── Status ───────────────────────────────────────────────

  completed(): this {
    assertStatus(this.result, 'COMPLETED');
    return this;
  }

  failed(): this {
    assertStatus(this.result, 'FAILED');
    return this;
  }

  status(s: string): this {
    assertStatus(this.result, s);
    return this;
  }

  noErrors(): this {
    assertNoErrors(this.result);
    return this;
  }

  // ── Tools ────────────────────────────────────────────────

  usedTool(
    name: string,
    opts?: { args?: Record<string, unknown> },
  ): this {
    if (opts?.args) {
      assertToolCalledWith(this.result, name, opts.args);
    } else {
      assertToolUsed(this.result, name);
    }
    return this;
  }

  didNotUseTool(name: string): this {
    assertToolNotUsed(this.result, name);
    return this;
  }

  toolCallOrder(names: string[]): this {
    assertToolCallOrder(this.result, names);
    return this;
  }

  toolsUsedExactly(names: string[]): this {
    assertToolsUsedExactly(this.result, names);
    return this;
  }

  // ── Output ───────────────────────────────────────────────

  outputContains(
    text: string,
    opts?: { caseSensitive?: boolean },
  ): this {
    assertOutputContains(this.result, text, opts);
    return this;
  }

  outputMatches(pattern: string | RegExp): this {
    assertOutputMatches(this.result, pattern);
    return this;
  }

  outputType(typeName: string): this {
    assertOutputType(this.result, typeName);
    return this;
  }

  // ── Events ───────────────────────────────────────────────

  eventsContain(
    eventType: string,
    opts?: { expected?: boolean },
  ): this {
    assertEventsContain(this.result, eventType, opts);
    return this;
  }

  eventSequence(types: string[]): this {
    assertEventSequence(this.result, types);
    return this;
  }

  // ── Multi-agent ──────────────────────────────────────────

  handoffTo(agentName: string): this {
    assertHandoffTo(this.result, agentName);
    return this;
  }

  agentRan(agentName: string): this {
    assertAgentRan(this.result, agentName);
    return this;
  }

  // ── Guardrails ───────────────────────────────────────────

  guardrailPassed(name: string): this {
    assertGuardrailPassed(this.result, name);
    return this;
  }

  guardrailFailed(name: string): this {
    assertGuardrailFailed(this.result, name);
    return this;
  }

  // ── Budget ───────────────────────────────────────────────

  maxTurns(n: number): this {
    assertMaxTurns(this.result, n);
    return this;
  }
}

export function expect(result: AgentResult): AgentResultExpectation {
  return new AgentResultExpectation(result);
}
