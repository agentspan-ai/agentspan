/**
 * Supply Chain -- multi-agent supply chain management.
 *
 * Demonstrates:
 *   - Coordinator delegates to inventory, logistics, and demand specialists
 *   - Each specialist has domain-specific tools
 *   - Complex multi-agent workflow for supply chain analysis
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Inventory tools ───────────────────────────────────────────────

const getInventoryLevels = new FunctionTool({
  name: 'get_inventory_levels',
  description: 'Get current inventory levels at a warehouse.',
  parameters: z.object({
    warehouse: z.string().describe('Warehouse name (e.g., "west", "east")'),
  }),
  execute: async (args: { warehouse: string }) => {
    const warehouses: Record<string, {
      warehouse: string;
      items: Array<{ sku: string; quantity: number; reorder_point: number }>;
    }> = {
      west: {
        warehouse: 'West Coast',
        items: [
          { sku: 'WIDGET-A', quantity: 5000, reorder_point: 2000 },
          { sku: 'WIDGET-B', quantity: 1200, reorder_point: 1500 },
          { sku: 'GADGET-X', quantity: 800, reorder_point: 500 },
        ],
      },
      east: {
        warehouse: 'East Coast',
        items: [
          { sku: 'WIDGET-A', quantity: 3200, reorder_point: 2000 },
          { sku: 'WIDGET-B', quantity: 4500, reorder_point: 1500 },
          { sku: 'GADGET-X', quantity: 200, reorder_point: 500 },
        ],
      },
    };
    return warehouses[args.warehouse.toLowerCase()] ?? { error: `Warehouse '${args.warehouse}' not found` };
  },
});

const checkSupplierStatus = new FunctionTool({
  name: 'check_supplier_status',
  description: 'Check supplier availability and lead times.',
  parameters: z.object({
    sku: z.string().describe('Product SKU'),
  }),
  execute: async (args: { sku: string }) => {
    const suppliers: Record<string, { supplier: string; lead_time_days: number; min_order: number; unit_cost: number }> = {
      'WIDGET-A': { supplier: 'WidgetCorp', lead_time_days: 14, min_order: 1000, unit_cost: 2.5 },
      'WIDGET-B': { supplier: 'WidgetCorp', lead_time_days: 21, min_order: 500, unit_cost: 4.75 },
      'GADGET-X': { supplier: 'GadgetWorks', lead_time_days: 30, min_order: 200, unit_cost: 12.0 },
    };
    return suppliers[args.sku.toUpperCase()] ?? { error: `No supplier for SKU ${args.sku}` };
  },
});

// ── Logistics tools ───────────────────────────────────────────────

const getShippingRoutes = new FunctionTool({
  name: 'get_shipping_routes',
  description: 'Get available shipping routes between warehouses.',
  parameters: z.object({
    origin: z.string().describe('Origin warehouse'),
    destination: z.string().describe('Destination warehouse'),
  }),
  execute: async (args: { origin: string; destination: string }) => ({
    origin: args.origin,
    destination: args.destination,
    routes: [
      { method: 'Ground', transit_days: 5, cost_per_unit: 0.5 },
      { method: 'Rail', transit_days: 3, cost_per_unit: 0.75 },
      { method: 'Air', transit_days: 1, cost_per_unit: 2.0 },
    ],
  }),
});

const getPendingShipments = new FunctionTool({
  name: 'get_pending_shipments',
  description: 'Get all pending shipments in the system.',
  parameters: z.object({}),
  execute: async () => ({
    shipments: [
      { id: 'SHP-001', sku: 'WIDGET-A', qty: 2000, status: 'in_transit', eta: '2025-04-18' },
      { id: 'SHP-002', sku: 'GADGET-X', qty: 500, status: 'processing', eta: '2025-05-01' },
    ],
  }),
});

// ── Demand tools ──────────────────────────────────────────────────

const getDemandForecast = new FunctionTool({
  name: 'get_demand_forecast',
  description: 'Get demand forecast for a SKU.',
  parameters: z.object({
    sku: z.string().describe('Product SKU'),
    weeks_ahead: z.number().describe('Number of weeks to forecast').default(4),
  }),
  execute: async (args: { sku: string; weeks_ahead?: number }) => {
    const weeksAhead = args.weeks_ahead ?? 4;
    const forecasts: Record<string, { weekly_demand: number; trend: string; confidence: number }> = {
      'WIDGET-A': { weekly_demand: 800, trend: 'increasing', confidence: 0.85 },
      'WIDGET-B': { weekly_demand: 300, trend: 'stable', confidence: 0.9 },
      'GADGET-X': { weekly_demand: 150, trend: 'decreasing', confidence: 0.75 },
    };
    const data = forecasts[args.sku.toUpperCase()] ?? { weekly_demand: 0, trend: 'unknown', confidence: 0 };
    return {
      sku: args.sku,
      weeks_ahead: weeksAhead,
      ...data,
      total_forecast: data.weekly_demand * weeksAhead,
    };
  },
});

// ── Sub-agents ────────────────────────────────────────────────────

export const inventoryAgent = new LlmAgent({
  name: 'inventory_manager',
  model,
  description: 'Manages inventory levels and supplier relationships.',
  instruction: 'Check inventory levels and supplier status. Flag items below reorder points.',
  tools: [getInventoryLevels, checkSupplierStatus],
});

export const logisticsAgent = new LlmAgent({
  name: 'logistics_coordinator',
  model,
  description: 'Handles shipping routes and shipment tracking.',
  instruction: 'Find optimal shipping routes and track pending shipments.',
  tools: [getShippingRoutes, getPendingShipments],
});

export const demandAgent = new LlmAgent({
  name: 'demand_planner',
  model,
  description: 'Forecasts product demand.',
  instruction: 'Analyze demand forecasts and identify trends.',
  tools: [getDemandForecast],
});

// ── Coordinator ───────────────────────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'supply_chain_coordinator',
  model,
  instruction:
    'You are a supply chain coordinator. Analyze inventory, logistics, and demand. ' +
    'Identify items that need restocking, recommend optimal shipping, and provide ' +
    'an action plan. Delegate to the appropriate specialist.',
  subAgents: [inventoryAgent, logisticsAgent, demandAgent],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(coordinator);
    await runtime.serve(coordinator);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // coordinator,
    // 'Give me a full supply chain status report. Check both warehouses, ' +
    // 'identify any items below reorder points, and recommend restocking actions.',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('19-supply-chain.ts') || process.argv[1]?.endsWith('19-supply-chain.js')) {
  main().catch(console.error);
}
