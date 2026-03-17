'use strict';

/**
 * Agent — primary abstraction for defining AI agents.
 *
 * @example
 * const agent = new Agent({
 *   name: 'weather_agent',
 *   model: 'openai/gpt-4o',
 *   instructions: 'You are a helpful weather assistant.',
 *   tools: [getWeather],
 * })
 */

class Agent {
  constructor(options) {
    if (!options || !options.name) {
      throw new Error('Agent requires a name');
    }

    this.name = options.name;
    this.model = options.model || '';
    this.instructions = options.instructions || null;
    this.tools = options.tools || [];
    this.agents = options.agents || [];
    this.strategy = options.strategy || null;
    this.router = options.router || null;
    this.maxTurns = options.maxTurns || 25;
    this.maxTokens = options.maxTokens || null;
    this.temperature = options.temperature != null ? options.temperature : null;
    this.timeoutSeconds = options.timeoutSeconds || null;
    this.external = options.external || false;
    this.metadata = options.metadata || {};
  }
}

module.exports = { Agent };
