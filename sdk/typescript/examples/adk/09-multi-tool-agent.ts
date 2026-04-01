/**
 * Google ADK Agent with Multiple Specialized Tools -- complex tool orchestration.
 *
 * Demonstrates:
 *   - Multiple tools working together for a complex task
 *   - Tools with various parameter types and return structures
 *   - Best practice: dict returns with "status" field
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

const searchProducts = new FunctionTool({
  name: 'search_products',
  description: 'Search the product catalog.',
  parameters: z.object({
    query: z.string().describe('Search query string'),
    category: z.string().describe('Product category: "electronics", "books", "clothing", or "all"').default('all'),
    max_results: z.number().describe('Maximum number of results to return').default(5),
  }),
  execute: async (args: { query: string; category?: string; max_results?: number }) => {
    const category = args.category ?? 'all';
    const maxResults = args.max_results ?? 5;
    const products = [
      { id: 'P001', name: 'Wireless Mouse', category: 'electronics', price: 29.99, rating: 4.5 },
      { id: 'P002', name: 'Python Cookbook', category: 'books', price: 45.0, rating: 4.8 },
      { id: 'P003', name: 'USB-C Hub', category: 'electronics', price: 39.99, rating: 4.2 },
      { id: 'P004', name: 'Ergonomic Keyboard', category: 'electronics', price: 89.99, rating: 4.7 },
      { id: 'P005', name: 'Clean Code', category: 'books', price: 35.0, rating: 4.9 },
    ];
    const queryLower = args.query.toLowerCase();
    const results = products.filter(
      (p) => p.name.toLowerCase().includes(queryLower) || (category !== 'all' && p.category === category),
    );
    return { status: 'success', results: results.slice(0, maxResults), total: results.length };
  },
});

const checkInventory = new FunctionTool({
  name: 'check_inventory',
  description: 'Check inventory availability for a product.',
  parameters: z.object({
    product_id: z.string().describe('The product ID to check'),
  }),
  execute: async (args: { product_id: string }) => {
    const inventory: Record<string, { in_stock: boolean; quantity: number; warehouse?: string; restock_date?: string }> = {
      P001: { in_stock: true, quantity: 150, warehouse: 'West' },
      P002: { in_stock: true, quantity: 45, warehouse: 'East' },
      P003: { in_stock: false, quantity: 0, restock_date: '2025-04-01' },
      P004: { in_stock: true, quantity: 8, warehouse: 'West' },
      P005: { in_stock: true, quantity: 200, warehouse: 'East' },
    };
    const item = inventory[args.product_id];
    if (item) {
      return { status: 'success', product_id: args.product_id, ...item };
    }
    return { status: 'error', message: `Product ${args.product_id} not found` };
  },
});

const calculateShipping = new FunctionTool({
  name: 'calculate_shipping',
  description: 'Calculate shipping cost for a list of products.',
  parameters: z.object({
    product_ids: z.array(z.string()).describe('List of product IDs to ship'),
    destination: z.string().describe('Shipping destination (city or zip code)'),
  }),
  execute: async (args: { product_ids: string[]; destination: string }) => {
    const baseCost = args.product_ids.length * 5.99;
    return {
      status: 'success',
      destination: args.destination,
      items: args.product_ids.length,
      options: [
        { method: 'Standard (5-7 days)', cost: `$${baseCost.toFixed(2)}` },
        { method: 'Express (2-3 days)', cost: `$${(baseCost * 1.8).toFixed(2)}` },
        { method: 'Overnight', cost: `$${(baseCost * 3).toFixed(2)}` },
      ],
    };
  },
});

const applyCoupon = new FunctionTool({
  name: 'apply_coupon',
  description: 'Apply a coupon code to calculate the discount.',
  parameters: z.object({
    subtotal: z.number().describe('The order subtotal before discount'),
    coupon_code: z.string().describe('The coupon code to apply'),
  }),
  execute: async (args: { subtotal: number; coupon_code: string }) => {
    const coupons: Record<string, { type: string; value: number }> = {
      SAVE10: { type: 'percentage', value: 10 },
      FLAT20: { type: 'fixed', value: 20 },
      FREESHIP: { type: 'shipping', value: 0 },
    };
    const coupon = coupons[args.coupon_code.toUpperCase()];
    if (!coupon) {
      return { status: 'error', message: `Invalid coupon: ${args.coupon_code}` };
    }

    let discount: number;
    if (coupon.type === 'percentage') {
      discount = args.subtotal * coupon.value / 100;
    } else if (coupon.type === 'fixed') {
      discount = Math.min(coupon.value, args.subtotal);
    } else {
      discount = 0;
    }

    return {
      status: 'success',
      coupon: args.coupon_code,
      discount: `$${discount.toFixed(2)}`,
      final_price: `$${(args.subtotal - discount).toFixed(2)}`,
    };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'shopping_assistant',
  model,
  instruction:
    'You are a helpful shopping assistant. Help users find products, ' +
    'check availability, calculate shipping, and apply coupons. ' +
    'Always check inventory before recommending products. ' +
    'Present information in a clear, organized format.',
  tools: [searchProducts, checkInventory, calculateShipping, applyCoupon],
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
    "I'm looking for electronics. Show me what you have, check if they're " +
    'in stock, and calculate shipping to San Francisco. I have coupon code SAVE10.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('09-multi-tool-agent.ts') || process.argv[1]?.endsWith('09-multi-tool-agent.js')) {
  main().catch(console.error);
}
