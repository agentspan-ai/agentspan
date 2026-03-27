/**
 * 32 - Human-in-the-loop Guardrail (onFail='human')
 *
 * Demonstrates a guardrail that pauses the workflow for human review when
 * the output fails validation. The human can approve, reject, or edit.
 *
 * Since the workflow pauses at a HumanTask, this example uses start()
 * (async) instead of run() (blocking).
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, guardrail, tool } from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Guardrail ---------------------------------------------------------------

const complianceCheck = guardrail(
  (content: string): GuardrailResult => {
    const flaggedTerms = ['investment advice', 'guaranteed returns', 'risk-free'];
    for (const term of flaggedTerms) {
      if (content.toLowerCase().includes(term.toLowerCase())) {
        return {
          passed: false,
          message: `Response contains flagged term: '${term}'. Needs human review.`,
        };
      }
    }
    return { passed: true };
  },
  {
    name: 'compliance',
    position: 'output',
    onFail: 'human',
  },
);

// -- Tool --------------------------------------------------------------------

const getMarketData = tool(
  async (args: { ticker: string }) => {
    return {
      ticker: args.ticker,
      price: 185.42,
      change: '+2.3%',
      volume: '45.2M',
    };
  },
  {
    name: 'get_market_data',
    description: 'Get current market data for a stock ticker.',
    inputSchema: z.object({
      ticker: z.string().describe('The stock ticker symbol'),
    }),
  },
);

// -- Agent -------------------------------------------------------------------

export const agent = new Agent({
  name: 'finance_agent',
  model: llmModel,
  tools: [getMarketData],
  instructions:
    'You are a financial information assistant. Provide market data ' +
    'and general financial information. You may discuss investment ' +
    'strategies and returns.',
  guardrails: [complianceCheck],
});

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('32-human-guardrail.ts') || process.argv[1]?.endsWith('32-human-guardrail.js')) {
  const runtime = new AgentRuntime();
  try {
    // Start the agent (async -- does not block)
    const handle = await runtime.start(
      agent,
      'Look up AAPL and explain whether it\'s a good investment. ' +
      'Include your opinion on potential returns.',
    );
    console.log(`Workflow started: ${handle.workflowId}`);

    // Poll for status
    for (let i = 0; i < 60; i++) {
      const status = await handle.getStatus();
      console.log(`  Status: ${status.status} (waiting=${status.isWaiting})`);

      if (status.isWaiting) {
        console.log('\n--- Workflow paused for human review ---');
        console.log('The guardrail flagged the response for compliance review.');
        console.log('Options: approve(), reject(reason), or respond(output)');

        // In a real app, a human would review in the Conductor UI.
        // Here we auto-reject for the demo.
        console.log('Auto-rejecting for demo...');
        await handle.reject('bad idea');
        console.log('Rejected! Resuming workflow...\n');
      }

      if (status.isComplete) {
        console.log(`\nFinal output: ${status.output}`);
        break;
      }

      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } finally {
    await runtime.shutdown();
  }
}
