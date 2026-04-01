/**
 * 13 - Hierarchical Agents — nested agent teams.
 *
 * Demonstrates multi-level agent hierarchies where a top-level orchestrator
 * delegates to team leads, who in turn delegate to specialists.
 *
 * Structure:
 *     CEO Agent
 *     +-- Engineering Lead (handoff)
 *     |   +-- Backend Developer
 *     |   +-- Frontend Developer
 *     +-- Marketing Lead (handoff)
 *         +-- Content Writer
 *         +-- SEO Specialist
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

// ── Level 3: Individual specialists ─────────────────────────

export const backendDev = new Agent({
  name: 'backend_dev',
  model: llmModel,
  instructions:
    'You are a backend developer. You design APIs, databases, and server ' +
    'architecture. Provide technical recommendations with code examples.',
});

export const frontendDev = new Agent({
  name: 'frontend_dev',
  model: llmModel,
  instructions:
    'You are a frontend developer. You design UI components, user flows, ' +
    'and client-side architecture. Provide recommendations with code examples.',
});

export const contentWriter = new Agent({
  name: 'content_writer',
  model: llmModel,
  instructions:
    'You are a content writer. You create blog posts, landing page copy, ' +
    'and marketing materials. Write engaging, clear content.',
});

export const seoSpecialist = new Agent({
  name: 'seo_specialist',
  model: llmModel,
  instructions:
    'You are an SEO specialist. You optimize content for search engines, ' +
    'suggest keywords, and improve page rankings.',
});

// ── Level 2: Team leads (handoff to specialists) ───────────

export const engineeringLead = new Agent({
  name: 'engineering_lead',
  model: llmModel,
  instructions:
    'You are the engineering lead. Route technical questions to the right ' +
    'specialist: backend_dev for APIs/databases/servers, ' +
    'frontend_dev for UI/UX/client-side.',
  agents: [backendDev, frontendDev],
  strategy: 'handoff',
});

export const marketingLead = new Agent({
  name: 'marketing_lead',
  model: llmModel,
  instructions:
    'You are the marketing lead. Route marketing questions to the right ' +
    'specialist: content_writer for blog posts/copy, ' +
    'seo_specialist for SEO/keywords/rankings.',
  agents: [contentWriter, seoSpecialist],
  strategy: 'handoff',
});

// ── Level 1: CEO orchestrator (handoff to leads) ───────────

export const ceo = new Agent({
  name: 'ceo',
  model: llmModel,
  instructions:
    'You are the CEO. Route requests to the right department: ' +
    'engineering_lead for technical/development questions, ' +
    'marketing_lead for marketing/content/SEO questions. ' +
    'Delegate the entire request to the appropriate lead.',
  agents: [engineeringLead, marketingLead],
  strategy: 'handoff',
});

// ── Run ───────────────────────────────────────────────────

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(ceo);
    // await runtime.serve(ceo);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    console.log('--- Technical question (CEO -> Engineering -> Backend) ---');
    const result = await runtime.run(
    ceo,
    'Design a REST API for a user management system with authentication ' +
    'and then come up with a marketing campaign for the system',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('13-hierarchical-agents.ts') || process.argv[1]?.endsWith('13-hierarchical-agents.js')) {
  main().catch(console.error);
}
