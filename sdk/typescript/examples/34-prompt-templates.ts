/**
 * 34 - Prompt Templates
 *
 * Demonstrates using Conductor's prompt template system for agent instructions
 * and user prompts. Templates are created once on the server and referenced
 * by name -- promoting reuse, versioning, and centralized management.
 *
 * PromptTemplate supports:
 *   - name: Reference an existing template by name
 *   - variables: Substitute ${var} placeholders in the template
 *   - version: Pin to a specific version (undefined = latest)
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - Prompt templates created on the server (see setup below)
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, PromptTemplate, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Instructions from a template ---------------------------------
// The system prompt comes from a named template stored on the server.
// Variables are substituted at execution time by the Conductor server.

export const supportAgent = new Agent({
  name: 'support_agent',
  model: llmModel,
  instructions: new PromptTemplate(
    'customer-support',
    { company: 'Acme Corp', tone: 'friendly and professional' },
  ),
});

// -- Example 2: Template with tools ------------------------------------------

const lookupOrder = tool(
  async (args: { orderId: string }) => {
    return { order_id: args.orderId, status: 'shipped', eta: '2 days' };
  },
  {
    name: 'lookup_order',
    description: 'Look up an order by ID.',
    inputSchema: z.object({
      orderId: z.string().describe('The order ID'),
    }),
  },
);

const lookupCustomer = tool(
  async (args: { email: string }) => {
    return { email: args.email, name: 'Jane Doe', tier: 'premium' };
  },
  {
    name: 'lookup_customer',
    description: 'Look up customer details by email.',
    inputSchema: z.object({
      email: z.string().describe('Customer email address'),
    }),
  },
);

export const orderAgent = new Agent({
  name: 'order_assistant',
  model: llmModel,
  instructions: new PromptTemplate(
    'order-support',
    { max_refund: '$500', escalation_email: 'help@acme.com' },
  ),
  tools: [lookupOrder, lookupCustomer],
});

// -- Example 3: Pinned template version --------------------------------------
// Pin to a specific version for production stability.

export const stableAgent = new Agent({
  name: 'stable_agent',
  model: llmModel,
  instructions: new PromptTemplate('production-prompt', undefined, 3),
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(supportAgent);
    await runtime.serve(supportAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // // --- 1. Template-based instructions ---
    // console.log('=== Support Agent (template instructions) ===');
    // const result1 = await runtime.run(supportAgent, 'What are your return policies?');
    // result1.printResult();

    // // --- 2. Template with tools ---
    // console.log('\n=== Order Agent (template + tools) ===');
    // const result2 = await runtime.run(orderAgent, 'Can you check order #12345?');
    // result2.printResult();

    // // --- 3. User prompt from a template ---
    // // Note: In the TS SDK, PromptTemplate is supported for instructions
    // // (server-side resolution). For user prompts, resolve the template
    // // client-side since runtime.run() expects a string prompt.
    // console.log('\n=== User Prompt Template ===');
    // const result3 = await runtime.run(
    // stableAgent,
    // 'Please analyze Q4 2025 earnings trends and provide key insights with recommendations.',
    // );
    // result3.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('34-prompt-templates.ts') || process.argv[1]?.endsWith('34-prompt-templates.js')) {
  main().catch(console.error);
}
