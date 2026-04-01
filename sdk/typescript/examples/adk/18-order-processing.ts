/**
 * Order Processing -- end-to-end order management agent.
 *
 * Demonstrates:
 *   - Single agent handling complete order lifecycle
 *   - Catalog search, stock checking, pricing, and order placement
 *   - Multiple tools working together for a complex workflow
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

const searchCatalog = new FunctionTool({
  name: 'search_catalog',
  description: 'Search the product catalog.',
  parameters: z.object({
    query: z.string().describe('Search query string'),
    category: z.string().describe('Product category or "all"').default('all'),
  }),
  execute: async (args: { query: string; category?: string }) => {
    const category = args.category ?? 'all';
    const catalog = [
      { sku: 'LAP-001', name: 'ProBook Laptop 15"', category: 'laptops', price: 1299.99, stock: 23 },
      { sku: 'LAP-002', name: 'UltraSlim Notebook 13"', category: 'laptops', price: 899.99, stock: 45 },
      { sku: 'ACC-001', name: 'Wireless Mouse', category: 'accessories', price: 29.99, stock: 200 },
      { sku: 'ACC-002', name: 'USB-C Dock', category: 'accessories', price: 79.99, stock: 67 },
      { sku: 'MON-001', name: '4K Monitor 27"', category: 'monitors', price: 449.99, stock: 12 },
    ];
    const queryLower = args.query.toLowerCase();
    let results = catalog.filter(
      (item) =>
        (category === 'all' || item.category === category) &&
        (item.name.toLowerCase().includes(queryLower) || item.category.includes(queryLower)),
    );
    if (results.length === 0) {
      results = catalog.filter((item) => category === 'all' || item.category === category);
    }
    return { results: results.slice(0, 5), total_found: results.length };
  },
});

const checkStock = new FunctionTool({
  name: 'check_stock',
  description: 'Check real-time stock availability for a SKU.',
  parameters: z.object({
    sku: z.string().describe('The product SKU'),
  }),
  execute: async (args: { sku: string }) => {
    const stockData: Record<string, { available: boolean; quantity: number; warehouse: string }> = {
      'LAP-001': { available: true, quantity: 23, warehouse: 'West' },
      'LAP-002': { available: true, quantity: 45, warehouse: 'East' },
      'ACC-001': { available: true, quantity: 200, warehouse: 'Central' },
      'ACC-002': { available: true, quantity: 67, warehouse: 'Central' },
      'MON-001': { available: true, quantity: 12, warehouse: 'West' },
    };
    return stockData[args.sku.toUpperCase()] ?? { available: false, quantity: 0 };
  },
});

const calculateTotal = new FunctionTool({
  name: 'calculate_total',
  description: 'Calculate order total with tax and shipping. item_skus is a comma-separated list of SKUs.',
  parameters: z.object({
    item_skus: z.string().describe('Comma-separated list of SKUs'),
    shipping_method: z.string().describe('"standard", "express", or "overnight"').default('standard'),
  }),
  execute: async (args: { item_skus: string; shipping_method?: string }) => {
    const items = args.item_skus.split(',').map((s) => s.trim());
    const shippingMethod = args.shipping_method ?? 'standard';
    const prices: Record<string, number> = {
      'LAP-001': 1299.99,
      'LAP-002': 899.99,
      'ACC-001': 29.99,
      'ACC-002': 79.99,
      'MON-001': 449.99,
    };
    const shippingRates: Record<string, number> = { standard: 9.99, express: 24.99, overnight: 49.99 };

    const subtotal = items.reduce((sum, sku) => sum + (prices[sku] ?? 0), 0);
    const tax = Math.round(subtotal * 0.085 * 100) / 100;
    const shipping = shippingRates[shippingMethod] ?? 9.99;
    const total = Math.round((subtotal + tax + shipping) * 100) / 100;

    return { subtotal, tax, shipping, shipping_method: shippingMethod, total };
  },
});

const placeOrder = new FunctionTool({
  name: 'place_order',
  description: 'Place an order. item_skus is a comma-separated list of SKUs.',
  parameters: z.object({
    item_skus: z.string().describe('Comma-separated list of SKUs'),
    shipping_method: z.string().describe('Shipping method').default('standard'),
    payment_method: z.string().describe('Payment method').default('credit_card'),
  }),
  execute: async (args: { item_skus: string; shipping_method?: string; payment_method?: string }) => {
    const items = args.item_skus.split(',').map((s) => s.trim());
    const shippingMethod = args.shipping_method ?? 'standard';
    return {
      order_id: 'ORD-2025-0789',
      status: 'confirmed',
      items,
      shipping_method: shippingMethod,
      payment_method: args.payment_method ?? 'credit_card',
      estimated_delivery: shippingMethod === 'standard' ? '2025-04-22' : '2025-04-18',
    };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'order_processor',
  model,
  instruction:
    'You are an order processing assistant for TechMart. ' +
    'Help customers search products, check availability, calculate totals, and place orders. ' +
    'Always verify stock before confirming an order. Provide clear pricing breakdowns.',
  tools: [searchCatalog, checkStock, calculateTotal, placeOrder],
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
    "I need a laptop for work. Show me what's available, check stock for your recommendation, " +
    'and calculate the total with express shipping.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('18-order-processing.ts') || process.argv[1]?.endsWith('18-order-processing.js')) {
  main().catch(console.error);
}
