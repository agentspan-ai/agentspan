// ── Composable assertion functions for agent correctness testing ──────
//
// Every function takes an AgentResult as its first argument and throws
// an Error with a clear message on failure. They work identically whether
// the result came from mockRun or a live runtime.run() call.

import type { AgentResult, AgentEvent } from '../types.js';

// ── Tool assertions ──────────────────────────────────────────────────

export function assertToolUsed(result: AgentResult, name: string): void {
  const names = (result.toolCalls as Array<{ name?: string }>).map(
    (tc) => tc.name,
  );
  if (!names.includes(name)) {
    throw new Error(
      `Expected tool '${name}' to be used, but it was not.\nTools used: ${JSON.stringify(names)}`,
    );
  }
}

export function assertToolNotUsed(result: AgentResult, name: string): void {
  const names = (result.toolCalls as Array<{ name?: string }>).map(
    (tc) => tc.name,
  );
  if (names.includes(name)) {
    const count = names.filter((n) => n === name).length;
    throw new Error(
      `Expected tool '${name}' NOT to be used, but it was called ${count} time(s).\nTools used: ${JSON.stringify(names)}`,
    );
  }
}

export function assertToolCalledWith(
  result: AgentResult,
  name: string,
  args?: Record<string, unknown>,
): void {
  const matching = (
    result.toolCalls as Array<{ name?: string; args?: Record<string, unknown> }>
  ).filter((tc) => tc.name === name);

  if (matching.length === 0) {
    const allNames = (result.toolCalls as Array<{ name?: string }>).map(
      (tc) => tc.name,
    );
    throw new Error(
      `Expected tool '${name}' to be called, but it was not.\nTools used: ${JSON.stringify(allNames)}`,
    );
  }

  if (args == null) return;

  for (const tc of matching) {
    const tcArgs = tc.args ?? {};
    if (Object.entries(args).every(([k, v]) => tcArgs[k] === v)) {
      return;
    }
  }

  throw new Error(
    `Tool '${name}' was called but never with matching args.\n` +
      `Expected (subset): ${JSON.stringify(args)}\n` +
      `Actual calls: ${JSON.stringify(matching.map((tc) => tc.args))}`,
  );
}

export function assertToolCallOrder(
  result: AgentResult,
  names: string[],
): void {
  const actual = (result.toolCalls as Array<{ name?: string }>).map(
    (tc) => tc.name ?? '',
  );
  let idx = 0;
  for (const toolName of actual) {
    if (idx < names.length && toolName === names[idx]) {
      idx++;
    }
  }
  if (idx < names.length) {
    throw new Error(
      `Expected tool call order ${JSON.stringify(names)} (subsequence), ` +
        `but only matched up to index ${idx} ('${names[idx]}').\n` +
        `Actual tool calls: ${JSON.stringify(actual)}`,
    );
  }
}

export function assertToolsUsedExactly(
  result: AgentResult,
  names: string[],
): void {
  const actual = new Set(
    (result.toolCalls as Array<{ name?: string }>).map((tc) => tc.name ?? ''),
  );
  const expected = new Set(names);

  if (
    actual.size !== expected.size ||
    ![...actual].every((n) => expected.has(n))
  ) {
    const missing = [...expected].filter((n) => !actual.has(n));
    const extra = [...actual].filter((n) => !expected.has(n));
    const parts: string[] = [];
    if (missing.length) parts.push(`missing: ${JSON.stringify(missing)}`);
    if (extra.length) parts.push(`unexpected: ${JSON.stringify(extra)}`);
    throw new Error(
      `Expected exactly tools ${JSON.stringify([...expected].sort())}, ` +
        `got ${JSON.stringify([...actual].sort())}.\n${parts.join('; ')}`,
    );
  }
}

// ── Output assertions ────────────────────────────────────────────────

export function assertOutputContains(
  result: AgentResult,
  text: string,
  opts?: { caseSensitive?: boolean },
): void {
  const caseSensitive = opts?.caseSensitive ?? true;
  const output = JSON.stringify(result.output);
  const haystack = caseSensitive ? output : output.toLowerCase();
  const needle = caseSensitive ? text : text.toLowerCase();

  if (!haystack.includes(needle)) {
    const preview =
      output.length > 200 ? output.slice(0, 200) + '...' : output;
    throw new Error(
      `Expected output to contain '${text}', but it does not.\nOutput: ${preview}`,
    );
  }
}

export function assertOutputMatches(
  result: AgentResult,
  pattern: string | RegExp,
): void {
  const output = JSON.stringify(result.output);
  const re = typeof pattern === 'string' ? new RegExp(pattern) : pattern;

  if (!re.test(output)) {
    const preview =
      output.length > 200 ? output.slice(0, 200) + '...' : output;
    throw new Error(
      `Expected output to match pattern '${pattern}', but it does not.\nOutput: ${preview}`,
    );
  }
}

export function assertOutputType(
  result: AgentResult,
  typeName: string,
): void {
  const actual = typeof result.output;
  if (actual !== typeName) {
    throw new Error(
      `Expected output to be ${typeName}, got ${actual}: ${JSON.stringify(result.output)}`,
    );
  }
}

// ── Status assertions ────────────────────────────────────────────────

export function assertStatus(result: AgentResult, status: string): void {
  if (result.status !== status) {
    throw new Error(
      `Expected status '${status}', got '${result.status}'.`,
    );
  }
}

export function assertNoErrors(result: AgentResult): void {
  const errors = result.events.filter((e) => e.type === 'error');
  if (errors.length > 0) {
    const messages = errors.map((e) => e.content ?? 'unknown error');
    throw new Error(
      `Expected no errors, but ${errors.length} error(s) occurred.\nError messages: ${JSON.stringify(messages)}`,
    );
  }
}

// ── Event assertions ─────────────────────────────────────────────────

export function assertEventsContain(
  result: AgentResult,
  eventType: string,
  opts?: { expected?: boolean; attrs?: Record<string, unknown> },
): void {
  const expected = opts?.expected ?? true;
  const attrs = opts?.attrs ?? {};

  const matching = result.events.filter(
    (ev) =>
      ev.type === eventType &&
      Object.entries(attrs).every(
        ([k, v]) => (ev as unknown as Record<string, unknown>)[k] === v,
      ),
  );

  if (expected && matching.length === 0) {
    const attrStr = Object.keys(attrs).length > 0
      ? ` with ${JSON.stringify(attrs)}`
      : '';
    throw new Error(
      `Expected event of type '${eventType}'${attrStr}, but none found.\n` +
        `Event types present: ${JSON.stringify(result.events.map((ev) => ev.type))}`,
    );
  }
  if (!expected && matching.length > 0) {
    const attrStr = Object.keys(attrs).length > 0
      ? ` with ${JSON.stringify(attrs)}`
      : '';
    throw new Error(
      `Expected NO event of type '${eventType}'${attrStr}, but found ${matching.length}.`,
    );
  }
}

export function assertEventSequence(
  result: AgentResult,
  types: string[],
): void {
  const actualTypes = result.events.map((ev) => ev.type);
  let idx = 0;
  for (const evType of actualTypes) {
    if (idx < types.length && evType === types[idx]) {
      idx++;
    }
  }
  if (idx < types.length) {
    throw new Error(
      `Expected event sequence ${JSON.stringify(types)} (subsequence), ` +
        `but only matched up to index ${idx} ('${types[idx]}').\n` +
        `Actual event types: ${JSON.stringify(actualTypes)}`,
    );
  }
}

// ── Multi-agent assertions ───────────────────────────────────────────

export function assertHandoffTo(
  result: AgentResult,
  agentName: string,
): void {
  const handoffs = result.events.filter(
    (ev) => ev.type === 'handoff' && ev.target === agentName,
  );
  if (handoffs.length === 0) {
    const allHandoffs = result.events
      .filter((ev) => ev.type === 'handoff')
      .map((ev) => ev.target);
    throw new Error(
      `Expected handoff to '${agentName}', but none found.\n` +
        `Handoffs that occurred: ${JSON.stringify(allHandoffs)}`,
    );
  }
}

export function assertAgentRan(
  result: AgentResult,
  agentName: string,
): void {
  assertHandoffTo(result, agentName);
}

// ── Guardrail assertions ─────────────────────────────────────────────

export function assertGuardrailPassed(
  result: AgentResult,
  name: string,
): void {
  const passing = result.events.filter(
    (ev) => ev.type === 'guardrail_pass' && ev.guardrailName === name,
  );
  if (passing.length === 0) {
    const allGuardrails = result.events
      .filter(
        (ev) =>
          ev.type === 'guardrail_pass' || ev.type === 'guardrail_fail',
      )
      .map((ev) => [ev.type, ev.guardrailName]);
    throw new Error(
      `Expected guardrail '${name}' to pass, but no matching event found.\n` +
        `Guardrail events: ${JSON.stringify(allGuardrails)}`,
    );
  }
}

export function assertGuardrailFailed(
  result: AgentResult,
  name: string,
): void {
  const failing = result.events.filter(
    (ev) => ev.type === 'guardrail_fail' && ev.guardrailName === name,
  );
  if (failing.length === 0) {
    const allGuardrails = result.events
      .filter(
        (ev) =>
          ev.type === 'guardrail_pass' || ev.type === 'guardrail_fail',
      )
      .map((ev) => [ev.type, ev.guardrailName]);
    throw new Error(
      `Expected guardrail '${name}' to fail, but no matching event found.\n` +
        `Guardrail events: ${JSON.stringify(allGuardrails)}`,
    );
  }
}

// ── Turn/iteration assertions ────────────────────────────────────────

export function assertMaxTurns(result: AgentResult, n: number): void {
  const turns = result.events.filter(
    (ev) => ev.type === 'tool_call' || ev.type === 'done',
  ).length;
  if (turns > n) {
    throw new Error(
      `Expected at most ${n} turn(s), but the agent took ${turns}.`,
    );
  }
}
