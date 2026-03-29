/**
 * Global Instruction -- globalInstruction for system-wide context.
 *
 * Demonstrates:
 *   - Using globalInstruction for context shared across all agents
 *   - instruction is specific to each agent
 *   - Store assistant with product lookup and store hours tools
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

const getProductInfo = new FunctionTool({
  name: 'get_product_info',
  description: 'Look up product information.',
  parameters: z.object({
    product_name: z.string().describe('Name of the product to look up'),
  }),
  execute: async (args: { product_name: string }) => {
    const products: Record<string, { name: string; price: number; category: string; in_stock: boolean; rating: number }> = {
      'widget pro': {
        name: 'Widget Pro',
        price: 49.99,
        category: 'electronics',
        in_stock: true,
        rating: 4.7,
      },
      'gadget max': {
        name: 'Gadget Max',
        price: 89.99,
        category: 'electronics',
        in_stock: false,
        rating: 4.2,
      },
      'smart lamp': {
        name: 'Smart Lamp',
        price: 34.99,
        category: 'home',
        in_stock: true,
        rating: 4.5,
      },
    };
    return products[args.product_name.toLowerCase()] ?? { error: `Product '${args.product_name}' not found` };
  },
});

const getStoreHours = new FunctionTool({
  name: 'get_store_hours',
  description: 'Get store hours for a location.',
  parameters: z.object({
    location: z.string().describe('Store location name'),
  }),
  execute: async (args: { location: string }) => {
    const stores: Record<string, { hours: string; open_today: boolean }> = {
      downtown: { hours: '9 AM - 9 PM', open_today: true },
      mall: { hours: '10 AM - 8 PM', open_today: true },
    };
    return stores[args.location.toLowerCase()] ?? { error: `Location '${args.location}' not found` };
  },
});

// ── Agent with globalInstruction ────────────────────────────────────

export const agent = new LlmAgent({
  name: 'store_assistant',
  model,
  globalInstruction:
    'You work for TechStore, a premium electronics retailer. ' +
    'Always be professional and mention our satisfaction guarantee. ' +
    'Current promotion: 15% off all electronics this week.',
  instruction:
    'You are a store assistant. Help customers find products, ' +
    'check availability, and provide store hours. ' +
    'Always mention the current promotion when discussing electronics.',
  tools: [getProductInfo, getStoreHours],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // agent,
    // "I'm looking for the Widget Pro. Is it in stock? Also, what are the downtown store hours?",
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('15-global-instruction.ts') || process.argv[1]?.endsWith('15-global-instruction.js')) {
  main().catch(console.error);
}
