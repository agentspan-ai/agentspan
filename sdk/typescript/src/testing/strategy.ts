import type { Strategy } from '../types.js';
import { Agent } from '../agent.js';

/**
 * Validate that an agent's strategy matches the expected value.
 * Throws if it does not match.
 */
export function validateStrategy(agent: Agent, expected: Strategy): void {
  if (agent.strategy !== expected) {
    throw new Error(
      `Expected strategy "${expected}", got "${agent.strategy}"`,
    );
  }
}
