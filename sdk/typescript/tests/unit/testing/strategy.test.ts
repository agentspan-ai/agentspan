import { describe, it, expect } from 'vitest';
import {
  validateStrategy,
  validateSequential,
  validateParallel,
  validateRoundRobin,
  validateRouter,
  validateHandoff,
  validateSwarm,
  validateConstrainedTransitions,
  StrategyViolation,
} from '../../../src/testing/strategy.js';
import { Agent } from '../../../src/agent.js';
import { makeAgentResult } from '../../../src/result.js';
import type { AgentEvent } from '../../../src/types.js';

// ── Helpers ──────────────────────────────────────────────

function makeResult(events: AgentEvent[]) {
  return makeAgentResult({
    executionId: 'wf-test',
    status: 'COMPLETED',
    events,
  });
}

function makeAgent(opts: {
  name: string;
  strategy?: string;
  agents?: Agent[];
  maxTurns?: number;
  allowedTransitions?: Record<string, string[]>;
  router?: Agent;
}) {
  return new Agent({
    name: opts.name,
    strategy: opts.strategy as any,
    agents: opts.agents,
    maxTurns: opts.maxTurns,
    allowedTransitions: opts.allowedTransitions,
    router: opts.router,
  });
}

// ── StrategyViolation ────────────────────────────────────

describe('StrategyViolation', () => {
  it('has strategy and violations properties', () => {
    const err = new StrategyViolation('sequential', ['missed A', 'missed B']);
    expect(err.strategy).toBe('sequential');
    expect(err.violations).toEqual(['missed A', 'missed B']);
    expect(err.message).toContain('sequential');
    expect(err.message).toContain('missed A');
  });
});

// ── validateSequential ───────────────────────────────────

describe('validateSequential', () => {
  it('passes when all agents run in order', () => {
    const agent = makeAgent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [
        new Agent({ name: 'a' }),
        new Agent({ name: 'b' }),
        new Agent({ name: 'c' }),
      ],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'c' },
    ]);

    expect(() => validateSequential(agent, result)).not.toThrow();
  });

  it('throws when agent is skipped', () => {
    const agent = makeAgent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([{ type: 'handoff', target: 'a' }]);

    expect(() => validateSequential(agent, result)).toThrow(StrategyViolation);
  });

  it('throws when order is wrong', () => {
    const agent = makeAgent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
    ]);

    expect(() => validateSequential(agent, result)).toThrow(StrategyViolation);
  });

  it('throws when agent runs multiple times', () => {
    const agent = makeAgent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
    ]);

    expect(() => validateSequential(agent, result)).toThrow(/multiple times/);
  });

  it('passes with no sub-agents', () => {
    const agent = makeAgent({ name: 'simple', strategy: 'sequential' });
    const result = makeResult([]);
    expect(() => validateSequential(agent, result)).not.toThrow();
  });
});

// ── validateParallel ─────────────────────────────────────

describe('validateParallel', () => {
  it('passes when all agents run', () => {
    const agent = makeAgent({
      name: 'parallel',
      strategy: 'parallel',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
    ]);

    expect(() => validateParallel(agent, result)).not.toThrow();
  });

  it('throws when an agent is missing', () => {
    const agent = makeAgent({
      name: 'parallel',
      strategy: 'parallel',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([{ type: 'handoff', target: 'a' }]);

    expect(() => validateParallel(agent, result)).toThrow(StrategyViolation);
  });
});

// ── validateRoundRobin ───────────────────────────────────

describe('validateRoundRobin', () => {
  it('passes with correct alternation', () => {
    const agent = makeAgent({
      name: 'rr',
      strategy: 'round_robin',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
    ]);

    expect(() => validateRoundRobin(agent, result)).not.toThrow();
  });

  it('throws on consecutive repeats', () => {
    const agent = makeAgent({
      name: 'rr',
      strategy: 'round_robin',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'a' },
    ]);

    expect(() => validateRoundRobin(agent, result)).toThrow(StrategyViolation);
  });

  it('throws when exceeding max_turns', () => {
    const agent = makeAgent({
      name: 'rr',
      strategy: 'round_robin',
      maxTurns: 2,
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
    ]);

    expect(() => validateRoundRobin(agent, result)).toThrow(/max_turns/);
  });
});

// ── validateRouter ───────────────────────────────────────

describe('validateRouter', () => {
  it('passes when exactly one agent selected', () => {
    const mockRouter = new Agent({ name: 'mock_router' });
    const agent = makeAgent({
      name: 'router',
      strategy: 'router',
      router: mockRouter,
      agents: [new Agent({ name: 'billing' }), new Agent({ name: 'tech' })],
    });
    const result = makeResult([{ type: 'handoff', target: 'billing' }]);

    expect(() => validateRouter(agent, result)).not.toThrow();
  });

  it('throws when multiple agents selected', () => {
    const mockRouter = new Agent({ name: 'mock_router' });
    const agent = makeAgent({
      name: 'router',
      strategy: 'router',
      router: mockRouter,
      agents: [new Agent({ name: 'billing' }), new Agent({ name: 'tech' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'billing' },
      { type: 'handoff', target: 'tech' },
    ]);

    expect(() => validateRouter(agent, result)).toThrow(/multiple agents/);
  });

  it('throws when no agent selected', () => {
    const mockRouter = new Agent({ name: 'mock_router' });
    const agent = makeAgent({
      name: 'router',
      strategy: 'router',
      router: mockRouter,
      agents: [new Agent({ name: 'billing' })],
    });
    const result = makeResult([]);

    expect(() => validateRouter(agent, result)).toThrow(/No sub-agent/);
  });
});

// ── validateHandoff ──────────────────────────────────────

describe('validateHandoff', () => {
  it('passes when handoff occurs to valid sub-agent', () => {
    const agent = makeAgent({
      name: 'coordinator',
      strategy: 'handoff',
      agents: [new Agent({ name: 'specialist' })],
    });
    const result = makeResult([{ type: 'handoff', target: 'specialist' }]);

    expect(() => validateHandoff(agent, result)).not.toThrow();
  });

  it('throws when no handoff occurs', () => {
    const agent = makeAgent({
      name: 'coordinator',
      strategy: 'handoff',
      agents: [new Agent({ name: 'specialist' })],
    });
    const result = makeResult([]);

    expect(() => validateHandoff(agent, result)).toThrow(/No handoff/);
  });
});

// ── validateSwarm ────────────────────────────────────────

describe('validateSwarm', () => {
  it('passes with valid transfers', () => {
    const agent = makeAgent({
      name: 'swarm',
      strategy: 'swarm',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
    ]);

    expect(() => validateSwarm(agent, result)).not.toThrow();
  });

  it('throws when no agent handles request', () => {
    const agent = makeAgent({
      name: 'swarm',
      strategy: 'swarm',
      agents: [new Agent({ name: 'a' })],
    });
    const result = makeResult([]);

    expect(() => validateSwarm(agent, result)).toThrow(/No agent handled/);
  });

  it('detects transfer loops', () => {
    const agent = makeAgent({
      name: 'swarm',
      strategy: 'swarm',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
    ]);

    expect(() => validateSwarm(agent, result)).toThrow(/loop/);
  });
});

// ── validateConstrainedTransitions ───────────────────────

describe('validateConstrainedTransitions', () => {
  it('passes when all transitions are allowed', () => {
    const agent = makeAgent({
      name: 'constrained',
      strategy: 'handoff',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
      allowedTransitions: { a: ['b'], b: ['a'] },
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
    ]);

    expect(() =>
      validateConstrainedTransitions(agent, result),
    ).not.toThrow();
  });

  it('throws on invalid transition', () => {
    const agent = makeAgent({
      name: 'constrained',
      strategy: 'handoff',
      agents: [
        new Agent({ name: 'a' }),
        new Agent({ name: 'b' }),
        new Agent({ name: 'c' }),
      ],
      allowedTransitions: { a: ['b'], b: ['c'] },
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'c' },
    ]);

    expect(() =>
      validateConstrainedTransitions(agent, result),
    ).toThrow(/Invalid transition/);
  });
});

// ── validateStrategy (dispatcher) ────────────────────────

describe('validateStrategy', () => {
  it('dispatches to the correct validator based on strategy', () => {
    const agent = makeAgent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
    ]);

    expect(() => validateStrategy(agent, result)).not.toThrow();
  });

  it('also validates constrained transitions when present', () => {
    const agent = makeAgent({
      name: 'constrained',
      strategy: 'handoff',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
      allowedTransitions: { a: ['b'] },
    });
    const result = makeResult([
      { type: 'handoff', target: 'a' },
      { type: 'handoff', target: 'b' },
    ]);

    expect(() => validateStrategy(agent, result)).not.toThrow();
  });

  it('throws when strategy fails', () => {
    const agent = makeAgent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [new Agent({ name: 'a' }), new Agent({ name: 'b' })],
    });
    const result = makeResult([{ type: 'handoff', target: 'a' }]);

    expect(() => validateStrategy(agent, result)).toThrow(StrategyViolation);
  });
});
