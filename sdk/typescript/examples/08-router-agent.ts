/**
 * Router Agent — LLM-based routing to specialists.
 *
 * Demonstrates the router strategy where a parent agent routes
 * to the appropriate sub-agent based on the user's request.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Specialist agents -------------------------------------------------------

const planner = new Agent({
  name: 'planner',
  model: llmModel,
  instructions:
    'You create implementation plans. Break down tasks into clear numbered steps.',
});

const coder = new Agent({
  name: 'coder',
  model: llmModel,
  instructions:
    'You write code. Output clean, well-documented Python code.',
});

const reviewer = new Agent({
  name: 'reviewer',
  model: llmModel,
  instructions:
    'You review code. Check for bugs, style issues, and suggest improvements.',
});

// -- Router (LLM decides who to use) ----------------------------------------

const team = new Agent({
  name: 'dev_team',
  model: llmModel,
  instructions:
    'You are the tech lead. Route requests to the right team member: ' +
    'planner for design/architecture, coder for implementation, ' +
    'reviewer for code review.',
  agents: [planner, coder, reviewer],
  strategy: 'router',
  router: planner, // Required for router strategy
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(
    team,
    'Write a Python function to validate email addresses using regex',
  );
  result.printResult();
} finally {
  await runtime.shutdown();
}
