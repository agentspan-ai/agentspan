/**
 * Agent Introductions -- agents introduce themselves before a discussion.
 *
 * Demonstrates the `introduction` parameter on Agent, which adds a
 * self-introduction to the conversation transcript at the start of
 * multi-agent group chats (round_robin, random, swarm, manual).
 *
 * This helps agents understand who they're collaborating with and
 * establishes context for the discussion.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

// -- Agents with introductions ---------------------------------------------

export const architect = new Agent({
  name: 'architect',
  model: llmModel,
  introduction:
    'I am the Software Architect. I focus on system design, scalability, ' +
    "and technical trade-offs. I'll evaluate proposals from an architecture " +
    'perspective.',
  instructions:
    'You are a software architect. Focus on system design, scalability, ' +
    'and architectural patterns. Keep responses to 2-3 paragraphs.',
});

export const securityEngineer = new Agent({
  name: 'security_engineer',
  model: llmModel,
  introduction:
    'I am the Security Engineer. I focus on threat modeling, authentication, ' +
    "authorization, and data protection. I'll flag any security concerns.",
  instructions:
    'You are a security engineer. Focus on security implications, ' +
    'vulnerabilities, and best practices. Keep responses to 2-3 paragraphs.',
});

export const productManager = new Agent({
  name: 'product_manager',
  model: llmModel,
  introduction:
    'I am the Product Manager. I focus on user needs, business value, ' +
    "and delivery timelines. I'll ensure we stay focused on what matters " +
    'to customers.',
  instructions:
    'You are a product manager. Focus on user needs, business value, ' +
    'and prioritization. Keep responses to 2-3 paragraphs.',
});

// -- Team discussion with introductions ------------------------------------

// Introductions are automatically prepended to the conversation transcript
// before the first turn, so each agent knows who's in the room.
export const designReview = new Agent({
  name: 'design_review',
  model: llmModel,
  agents: [architect, securityEngineer, productManager],
  strategy: 'round_robin',
  maxTurns: 6,
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(designReview);
    // await runtime.serve(designReview);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    designReview,
    'We need to design a new user authentication system for our SaaS platform. ' +
    'Should we use OAuth 2.0, SAML, or build our own JWT-based system?',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('29-agent-introductions.ts') || process.argv[1]?.endsWith('29-agent-introductions.js')) {
  main().catch(console.error);
}
