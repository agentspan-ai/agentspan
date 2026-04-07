// ── Strategy validators — verify that an execution trace obeys strategy rules ──
//
// These validators inspect an AgentResult and the Agent definition to verify
// that the orchestration pattern was actually followed. Unlike simple assertions,
// these validate the structural correctness of the entire execution trace.

import type { AgentResult, AgentEvent } from '../types.js';
import type { Agent } from '../agent.js';

// ── Helpers ──────────────────────────────────────────────────────────

function getAgentNames(agent: Agent): string[] {
  return (agent.agents ?? []).map((a) => a.name);
}

function getHandoffTargets(result: AgentResult): string[] {
  return result.events
    .filter((ev) => ev.type === 'handoff' && ev.target)
    .map((ev) => ev.target!);
}

function getStrategy(agent: Agent): string {
  return agent.strategy ?? 'handoff';
}

// ── StrategyViolation ────────────────────────────────────────────────

export class StrategyViolation extends Error {
  readonly strategy: string;
  readonly violations: string[];

  constructor(strategy: string, violations: string[]) {
    const msg =
      `Strategy '${strategy}' violations:\n` +
      violations.map((v) => `  - ${v}`).join('\n');
    super(msg);
    this.name = 'StrategyViolation';
    this.strategy = strategy;
    this.violations = violations;
  }
}

// ── Individual strategy validators ───────────────────────────────────

export function validateSequential(agent: Agent, result: AgentResult): void {
  const expected = getAgentNames(agent);
  if (expected.length === 0) return;

  const handoffs = getHandoffTargets(result);
  const violations: string[] = [];

  // Rule 1: All agents must appear
  const missing = expected.filter((n) => !handoffs.includes(n));
  if (missing.length > 0) {
    violations.push(
      `Agents skipped (never ran): ${JSON.stringify(missing.sort())}. Expected all of: ${JSON.stringify(expected)}`,
    );
  }

  // Rule 2: Order must match definition order
  const expectedSet = new Set(expected);
  const relevant = handoffs.filter((h) => expectedSet.has(h));
  let idx = 0;
  for (const h of relevant) {
    if (idx < expected.length && h === expected[idx]) {
      idx++;
    }
  }
  if (idx < expected.length && missing.length === 0) {
    violations.push(
      `Agents executed out of order. Expected: ${JSON.stringify(expected)}, got: ${JSON.stringify(relevant)}`,
    );
  }

  // Rule 3: No agent should run more than once
  const counts = new Map<string, number>();
  for (const h of relevant) {
    counts.set(h, (counts.get(h) ?? 0) + 1);
  }
  const duplicates: Record<string, number> = {};
  for (const [name, cnt] of counts) {
    if (cnt > 1) duplicates[name] = cnt;
  }
  if (Object.keys(duplicates).length > 0) {
    violations.push(
      `Agents executed multiple times (should be once each): ${JSON.stringify(duplicates)}`,
    );
  }

  if (violations.length > 0) {
    throw new StrategyViolation('sequential', violations);
  }
}

export function validateParallel(agent: Agent, result: AgentResult): void {
  const expected = new Set(getAgentNames(agent));
  if (expected.size === 0) return;

  const handoffs = new Set(getHandoffTargets(result));
  const violations: string[] = [];

  const missing = [...expected].filter((n) => !handoffs.has(n));
  if (missing.length > 0) {
    const ran = [...expected].filter((n) => handoffs.has(n));
    violations.push(
      `Agents never executed (skipped): ${JSON.stringify(missing.sort())}. ` +
        `In parallel strategy ALL agents must run. ` +
        `Expected: ${JSON.stringify([...expected].sort())}, ran: ${JSON.stringify(ran.sort())}`,
    );
  }

  if (violations.length > 0) {
    throw new StrategyViolation('parallel', violations);
  }
}

export function validateRoundRobin(agent: Agent, result: AgentResult): void {
  const expected = getAgentNames(agent);
  if (expected.length === 0) return;

  const handoffs = getHandoffTargets(result);
  const maxTurns = agent.maxTurns ?? 25;
  const violations: string[] = [];

  // Rule 1: All agents must participate
  const missing = expected.filter((n) => !handoffs.includes(n));
  if (missing.length > 0) {
    violations.push(
      `Agents never got a turn: ${JSON.stringify(missing.sort())}. ` +
        `All agents must participate in round-robin.`,
    );
  }

  // Rule 2: Agents must follow the rotation pattern
  const expectedSet = new Set(expected);
  const relevant = handoffs.filter((h) => expectedSet.has(h));
  const numAgents = expected.length;
  for (let i = 0; i < relevant.length; i++) {
    const expectedAgent = expected[i % numAgents];
    if (relevant[i] !== expectedAgent) {
      violations.push(
        `Turn ${i}: expected '${expectedAgent}' but got '${relevant[i]}'. ` +
          `Round-robin pattern broken. ` +
          `Expected rotation: ${JSON.stringify(expected)}, actual sequence: ${JSON.stringify(relevant)}`,
      );
      break;
    }
  }

  // Rule 3: No agent runs twice in a row
  for (let i = 1; i < relevant.length; i++) {
    if (relevant[i] === relevant[i - 1]) {
      violations.push(
        `Agent '${relevant[i]}' ran twice in a row at positions ` +
          `${i - 1} and ${i}. Round-robin must alternate.`,
      );
      break;
    }
  }

  // Rule 4: Turn count
  if (relevant.length > maxTurns) {
    violations.push(
      `Exceeded max_turns: ${relevant.length} turns taken, limit is ${maxTurns}.`,
    );
  }

  if (violations.length > 0) {
    throw new StrategyViolation('round_robin', violations);
  }
}

export function validateRouter(agent: Agent, result: AgentResult): void {
  const expected = new Set(getAgentNames(agent));
  if (expected.size === 0) return;

  const handoffs = getHandoffTargets(result);
  const relevant = handoffs.filter((h) => expected.has(h));
  const violations: string[] = [];

  // Rule 1: At least one agent must be selected
  if (relevant.length === 0) {
    violations.push(
      `No sub-agent was selected by the router. ` +
        `Available agents: ${JSON.stringify([...expected].sort())}, handoffs: ${JSON.stringify(handoffs)}`,
    );
  }

  // Rule 2: Only ONE agent should handle the request
  const uniqueAgents = new Set(relevant);
  if (uniqueAgents.size > 1) {
    violations.push(
      `Router selected multiple agents: ${JSON.stringify([...uniqueAgents].sort())}. ` +
        `Router strategy should route to exactly ONE specialist per request.`,
    );
  }

  // Rule 3: Selected agent must be a valid sub-agent
  const invalid = relevant.filter((h) => !expected.has(h));
  if (invalid.length > 0) {
    violations.push(
      `Router selected unknown agent(s): ${JSON.stringify([...new Set(invalid)].sort())}. ` +
        `Valid agents: ${JSON.stringify([...expected].sort())}`,
    );
  }

  if (violations.length > 0) {
    throw new StrategyViolation('router', violations);
  }
}

export function validateHandoff(agent: Agent, result: AgentResult): void {
  const expected = new Set(getAgentNames(agent));
  if (expected.size === 0) return;

  const handoffs = getHandoffTargets(result);
  const relevant = handoffs.filter((h) => expected.has(h));
  const violations: string[] = [];

  if (relevant.length === 0) {
    violations.push(
      `No handoff to any sub-agent occurred. ` +
        `Handoff strategy expects the parent to delegate to a specialist. ` +
        `Available agents: ${JSON.stringify([...expected].sort())}`,
    );
  }

  const invalid = handoffs.filter((h) => !expected.has(h));
  if (invalid.length > 0 && relevant.length === 0) {
    violations.push(
      `Handoff targets not in sub-agents: ${JSON.stringify([...new Set(invalid)].sort())}. ` +
        `Valid sub-agents: ${JSON.stringify([...expected].sort())}`,
    );
  }

  if (violations.length > 0) {
    throw new StrategyViolation('handoff', violations);
  }
}

export function validateSwarm(agent: Agent, result: AgentResult): void {
  const expected = new Set(getAgentNames(agent));
  if (expected.size === 0) return;

  const handoffs = getHandoffTargets(result);
  const maxTurns = agent.maxTurns ?? 25;
  const violations: string[] = [];

  // Rule 1: At least one agent must handle
  const relevant = handoffs.filter((h) => expected.has(h));
  if (relevant.length === 0) {
    violations.push(
      `No agent handled the request. Available agents: ${JSON.stringify([...expected].sort())}`,
    );
  }

  // Rule 2: All transfers must go to valid agents
  const invalid = handoffs.filter((h) => !expected.has(h));
  if (invalid.length > 0 && relevant.length === 0) {
    violations.push(
      `Transfer to unknown agent(s): ${JSON.stringify([...new Set(invalid)].sort())}. ` +
        `Valid agents: ${JSON.stringify([...expected].sort())}`,
    );
  }

  // Rule 3: Detect transfer loops
  if (relevant.length >= 2) {
    const pairCounts = new Map<string, number>();
    for (let i = 0; i < relevant.length - 1; i++) {
      const key = `${relevant[i]}->${relevant[i + 1]}`;
      pairCounts.set(key, (pairCounts.get(key) ?? 0) + 1);
    }
    const loops: Record<string, number> = {};
    for (const [pair, cnt] of pairCounts) {
      if (cnt > 2) loops[pair] = cnt;
    }
    if (Object.keys(loops).length > 0) {
      violations.push(
        `Possible transfer loop detected: ${JSON.stringify(loops)}. ` +
          `Same transfer pair repeated excessively.`,
      );
    }
  }

  // Rule 4: Total handoffs should not exceed max_turns
  if (relevant.length > maxTurns) {
    violations.push(
      `Too many transfers: ${relevant.length}, max_turns=${maxTurns}. Possible infinite loop.`,
    );
  }

  if (violations.length > 0) {
    throw new StrategyViolation('swarm', violations);
  }
}

export function validateConstrainedTransitions(
  agent: Agent,
  result: AgentResult,
): void {
  const allowed = agent.allowedTransitions;
  if (!allowed) return;

  const expectedAgents = new Set(getAgentNames(agent));
  const handoffs = getHandoffTargets(result).filter((h) =>
    expectedAgents.has(h),
  );
  const violations: string[] = [];

  for (let i = 0; i < handoffs.length - 1; i++) {
    const src = handoffs[i];
    const dst = handoffs[i + 1];
    const allowedNext = new Set(allowed[src] ?? []);
    if (!allowedNext.has(dst)) {
      violations.push(
        `Invalid transition: '${src}' → '${dst}' at turn ${i}. ` +
          `Allowed from '${src}': ${JSON.stringify([...allowedNext].sort())}`,
      );
    }
  }

  if (violations.length > 0) {
    throw new StrategyViolation('constrained_transitions', violations);
  }
}

// ── Dispatch ─────────────────────────────────────────────────────────

const VALIDATORS: Record<
  string,
  (agent: Agent, result: AgentResult) => void
> = {
  sequential: validateSequential,
  parallel: validateParallel,
  round_robin: validateRoundRobin,
  router: validateRouter,
  handoff: validateHandoff,
  swarm: validateSwarm,
};

export function validateStrategy(agent: Agent, result: AgentResult): void {
  const strategy = getStrategy(agent);
  const validator = VALIDATORS[strategy];
  if (validator) {
    validator(agent, result);
  }

  if (agent.allowedTransitions) {
    validateConstrainedTransitions(agent, result);
  }
}
