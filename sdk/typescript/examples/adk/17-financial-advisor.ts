/**
 * Financial Advisor -- multi-agent with specialized tool-using sub-agents.
 *
 * Demonstrates:
 *   - Coordinator agent with specialized sub-agents
 *   - Portfolio analyst, market researcher, and tax advisor
 *   - Each sub-agent has its own set of domain-specific tools
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Portfolio tools ───────────────────────────────────────────────

const getPortfolio = new FunctionTool({
  name: 'get_portfolio',
  description: 'Get the investment portfolio for a client.',
  parameters: z.object({
    client_id: z.string().describe('The client ID'),
  }),
  execute: async (args: { client_id: string }) => {
    const portfolios: Record<string, {
      client: string;
      total_value: number;
      holdings: Array<{ asset: string; shares?: number; units?: number; value: number }>;
      risk_profile: string;
    }> = {
      'CLT-001': {
        client: 'Sarah Chen',
        total_value: 250000,
        holdings: [
          { asset: 'AAPL', shares: 100, value: 17500 },
          { asset: 'GOOGL', shares: 50, value: 8750 },
          { asset: 'US Treasury Bonds', units: 200, value: 200000 },
          { asset: 'S&P 500 ETF', shares: 150, value: 23750 },
        ],
        risk_profile: 'moderate',
      },
    };
    return portfolios[args.client_id.toUpperCase()] ?? { error: `Client ${args.client_id} not found` };
  },
});

const calculateReturns = new FunctionTool({
  name: 'calculate_returns',
  description: 'Calculate returns for an asset over a period.',
  parameters: z.object({
    asset: z.string().describe('Asset name or ticker'),
    period_months: z.number().describe('Period in months').default(12),
  }),
  execute: async (args: { asset: string; period_months?: number }) => {
    const periodMonths = args.period_months ?? 12;
    const returns: Record<string, { return_pct: number; annualized: number }> = {
      AAPL: { return_pct: 15.2, annualized: 15.2 },
      GOOGL: { return_pct: 22.1, annualized: 22.1 },
      'US Treasury Bonds': { return_pct: 4.5, annualized: 4.5 },
      'S&P 500 ETF': { return_pct: 12.8, annualized: 12.8 },
    };
    const data = returns[args.asset] ?? { return_pct: 0, annualized: 0 };
    return { asset: args.asset, period_months: periodMonths, ...data };
  },
});

// ── Market tools ──────────────────────────────────────────────────

const getMarketData = new FunctionTool({
  name: 'get_market_data',
  description: 'Get current market data for a sector.',
  parameters: z.object({
    sector: z.string().describe('Market sector name'),
  }),
  execute: async (args: { sector: string }) => {
    const sectors: Record<string, Record<string, string | number>> = {
      technology: { trend: 'bullish', pe_ratio: 28.5, ytd_return: '18.3%' },
      healthcare: { trend: 'neutral', pe_ratio: 22.1, ytd_return: '8.7%' },
      energy: { trend: 'bearish', pe_ratio: 15.3, ytd_return: '-2.1%' },
      bonds: { trend: 'stable', yield: '4.5%', ytd_return: '3.2%' },
    };
    return sectors[args.sector.toLowerCase()] ?? { error: `Sector '${args.sector}' not found` };
  },
});

const getEconomicIndicators = new FunctionTool({
  name: 'get_economic_indicators',
  description: 'Get current key economic indicators.',
  parameters: z.object({}),
  execute: async () => ({
    gdp_growth: '2.1%',
    inflation: '3.2%',
    unemployment: '3.8%',
    fed_rate: '5.25%',
    consumer_confidence: 102.5,
  }),
});

// ── Tax tools ─────────────────────────────────────────────────────

const estimateTaxImpact = new FunctionTool({
  name: 'estimate_tax_impact',
  description: 'Estimate tax impact of selling an investment.',
  parameters: z.object({
    gains: z.number().describe('Capital gains amount'),
    holding_period_months: z.number().describe('How many months the asset was held'),
  }),
  execute: async (args: { gains: number; holding_period_months: number }) => {
    const isLongTerm = args.holding_period_months >= 12;
    const rate = isLongTerm ? 0.15 : 0.32;
    const category = isLongTerm ? 'long-term' : 'short-term';
    const tax = Math.round(args.gains * rate * 100) / 100;
    return {
      gains: args.gains,
      holding_period: `${args.holding_period_months} months`,
      category,
      tax_rate: `${rate * 100}%`,
      estimated_tax: tax,
    };
  },
});

// ── Sub-agents ────────────────────────────────────────────────────

export const portfolioAnalyst = new LlmAgent({
  name: 'portfolio_analyst',
  model,
  description: 'Analyzes client portfolios and calculates returns.',
  instruction: 'You are a portfolio analyst. Use tools to retrieve and analyze client portfolios.',
  tools: [getPortfolio, calculateReturns],
});

export const marketResearcher = new LlmAgent({
  name: 'market_researcher',
  model,
  description: 'Researches market conditions and economic indicators.',
  instruction: 'You are a market researcher. Provide sector analysis and economic outlook.',
  tools: [getMarketData, getEconomicIndicators],
});

export const taxAdvisor = new LlmAgent({
  name: 'tax_advisor',
  model,
  description: 'Advises on tax implications of investment decisions.',
  instruction: 'You are a tax advisor. Estimate tax impacts of proposed changes.',
  tools: [estimateTaxImpact],
});

// ── Coordinator ───────────────────────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'financial_advisor',
  model,
  instruction:
    'You are a senior financial advisor. Help clients with investment advice. ' +
    'Use the portfolio analyst to review holdings, market researcher for conditions, ' +
    'and tax advisor for tax implications. Provide a comprehensive recommendation.',
  subAgents: [portfolioAnalyst, marketResearcher, taxAdvisor],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(coordinator);
    // await runtime.serve(coordinator);
    // Direct run for local development:
    const result = await runtime.run(
    coordinator,
    "I'm client CLT-001. Review my portfolio and tell me if I should rebalance " +
    'given current market conditions. What would the tax impact be if I sold some AAPL?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('17-financial-advisor.ts') || process.argv[1]?.endsWith('17-financial-advisor.js')) {
  main().catch(console.error);
}
