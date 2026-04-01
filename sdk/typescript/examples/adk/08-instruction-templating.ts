/**
 * Google ADK Agent with Instruction Templating -- dynamic {variable} injection.
 *
 * Demonstrates:
 *   - ADK's instruction templating with {variable} syntax
 *   - Variables resolved from session state at runtime
 *   - Agent behavior changes based on injected context
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const getUserPreferences = new FunctionTool({
  name: 'get_user_preferences',
  description: 'Look up user preferences.',
  parameters: z.object({
    user_id: z.string().describe("The user's ID"),
  }),
  execute: async (args: { user_id: string }) => {
    const users: Record<string, { name: string; language: string; expertise: string; preferred_format: string }> = {
      user_001: {
        name: 'Alice',
        language: 'English',
        expertise: 'beginner',
        preferred_format: 'bullet points',
      },
      user_002: {
        name: 'Bob',
        language: 'English',
        expertise: 'advanced',
        preferred_format: 'detailed paragraphs',
      },
    };
    return users[args.user_id] ?? { name: 'Guest', expertise: 'intermediate', preferred_format: 'concise' };
  },
});

const searchTutorials = new FunctionTool({
  name: 'search_tutorials',
  description: 'Search for tutorials matching a topic and skill level.',
  parameters: z.object({
    topic: z.string().describe('Tutorial topic to search for'),
    level: z.string().describe('Skill level: beginner, intermediate, or advanced').default('intermediate'),
  }),
  execute: async (args: { topic: string; level?: string }) => {
    const level = (args.level ?? 'intermediate').toLowerCase();
    const tutorials: Record<string, string[]> = {
      'python-beginner': [
        'Python Basics: Variables and Types',
        'Your First Python Function',
        'Lists and Loops for Beginners',
      ],
      'python-advanced': [
        'Metaclasses and Descriptors',
        'Async IO Deep Dive',
        'CPython Internals',
      ],
    };
    const key = `${args.topic.toLowerCase()}-${level}`;
    const results = tutorials[key] ?? [`General ${args.topic} tutorial`];
    return { topic: args.topic, level, tutorials: results };
  },
});

// ── Agent with templated instructions ────────────────────────────────

// The {user_name} and {expertise_level} placeholders get replaced
// from session state when the agent runs in ADK.
export const agent = new LlmAgent({
  name: 'adaptive_tutor',
  model,
  instruction:
    'You are a personalized programming tutor. ' +
    'The current user is {user_name} with {expertise_level} expertise. ' +
    'Adapt your explanations to their level. ' +
    'Use the search_tutorials tool to find appropriate learning resources.',
  tools: [getUserPreferences, searchTutorials],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    const result = await runtime.run(
    agent,
    'I want to learn Python. What tutorials do you recommend?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('08-instruction-templating.ts') || process.argv[1]?.endsWith('08-instruction-templating.js')) {
  main().catch(console.error);
}
