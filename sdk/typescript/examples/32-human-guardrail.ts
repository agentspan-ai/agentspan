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
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime, guardrail, tool } from '@agentspan-ai/sdk';
import type { GuardrailResult } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

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
    inputSchema: {
      type: 'object',
      properties: {
        ticker: { type: 'string', description: 'The stock ticker symbol' },
      },
      required: ['ticker'],
    },
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

async function promptHuman(
  rl: readline.Interface,
  pendingTool: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const schema = (pendingTool.response_schema ?? {}) as Record<string, unknown>;
  const props = (schema.properties ?? {}) as Record<string, Record<string, unknown>>;
  const response: Record<string, unknown> = {};
  for (const [field, fs] of Object.entries(props)) {
    const desc = (fs.description || fs.title || field) as string;
    if (fs.type === 'boolean') {
      const val = await rl.question(`  ${desc} (y/n): `);
      response[field] = ['y', 'yes'].includes(val.trim().toLowerCase());
    } else {
      response[field] = await rl.question(`  ${desc}: `);
    }
  }
  return response;
}

const rl = readline.createInterface({ input: stdin, output: stdout });
const runtime = new AgentRuntime();
try {
  const handle = await runtime.start(
    agent,
    "Look up AAPL and explain whether it's a good investment. Include your opinion on potential returns.",
  );
  console.log(`Started: ${handle.executionId}\n`);

  for await (const event of handle.stream()) {
    if (event.type === 'thinking') {
      console.log(`  [thinking] ${event.content}`);
    } else if (event.type === 'tool_call') {
      console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
    } else if (event.type === 'tool_result') {
      console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result).slice(0, 100)}`);
    } else if (event.type === 'waiting') {
      const status = await handle.getStatus();
      const pt = (status.pendingTool ?? {}) as Record<string, unknown>;
      console.log('\n--- Human input required ---');
      const response = await promptHuman(rl, pt);
      await handle.respond(response);
      console.log();
    } else if (event.type === 'done') {
      console.log(`\nDone: ${JSON.stringify(event.output)}`);
    }
  }

  // Non-interactive alternative (no HITL, will block on human tasks):
  // const result = await runtime.run(agent, 'Look up AAPL and summarize the latest price movement.');
  // result.printResult();

  // Production pattern:
  // 1. Deploy once during CI/CD:
  // await runtime.deploy(agent);
  //
  // 2. In a separate long-lived worker process:
  // await runtime.serve(agent);
} finally {
  rl.close();
  await runtime.shutdown();
}
