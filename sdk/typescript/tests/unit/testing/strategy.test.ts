import { describe, it, expect } from 'vitest';
import { validateStrategy } from '../../../src/testing/strategy.js';
import { Agent } from '../../../src/agent.js';

describe('validateStrategy', () => {
  it('passes when strategy matches', () => {
    const agent = new Agent({
      name: 'pipeline',
      strategy: 'sequential',
      agents: [],
    });
    expect(() => validateStrategy(agent, 'sequential')).not.toThrow();
  });

  it('passes for handoff strategy', () => {
    const agent = new Agent({
      name: 'coordinator',
      strategy: 'handoff',
    });
    expect(() => validateStrategy(agent, 'handoff')).not.toThrow();
  });

  it('passes for parallel strategy', () => {
    const agent = new Agent({
      name: 'dispatcher',
      strategy: 'parallel',
    });
    expect(() => validateStrategy(agent, 'parallel')).not.toThrow();
  });

  it('throws when strategy does not match', () => {
    const agent = new Agent({
      name: 'pipeline',
      strategy: 'sequential',
    });
    expect(() => validateStrategy(agent, 'parallel')).toThrow(
      /Expected strategy "parallel", got "sequential"/,
    );
  });

  it('throws when agent has no strategy', () => {
    const agent = new Agent({ name: 'simple' });
    expect(() => validateStrategy(agent, 'handoff')).toThrow(
      /Expected strategy "handoff", got "undefined"/,
    );
  });

  it('supports router strategy', () => {
    const mockRouter = new Agent({ name: 'mock_router' });
    const agent = new Agent({
      name: 'router',
      strategy: 'router',
      router: mockRouter,
    });
    expect(() => validateStrategy(agent, 'router')).not.toThrow();
  });

  it('throws when strategy=router without router param', () => {
    expect(
      () => new Agent({ name: 'bad_router', strategy: 'router' }),
    ).toThrow(/no 'router' parameter was provided/);
  });

  it('supports swarm strategy', () => {
    const agent = new Agent({
      name: 'swarm',
      strategy: 'swarm',
    });
    expect(() => validateStrategy(agent, 'swarm')).not.toThrow();
  });
});
