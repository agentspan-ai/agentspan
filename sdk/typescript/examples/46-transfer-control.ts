/**
 * 46 - Transfer Control — constrained handoff paths between sub-agents.
 *
 * Uses `allowedTransitions` to restrict which agents can hand off to which.
 * This prevents unwanted transfers (e.g., a data collector shouldn't route
 * directly back to the coordinator).
 *
 * Requirements:
 *   - Conductor server
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Tools -------------------------------------------------------------------

const collectData = tool(
  async (args: { source: string }) => {
    return { source: args.source, records: 42, status: 'collected' };
  },
  {
    name: 'collect_data',
    description: 'Collect data from a source.',
    inputSchema: {
      type: 'object',
      properties: {
        source: { type: 'string', description: 'The data source name' },
      },
      required: ['source'],
    },
  },
);

const analyzeData = tool(
  async (args: { dataSummary: string }) => {
    return { analysis: 'Trend is upward', confidence: 0.87 };
  },
  {
    name: 'analyze_data',
    description: 'Analyze collected data.',
    inputSchema: {
      type: 'object',
      properties: {
        dataSummary: { type: 'string', description: 'Summary of data to analyze' },
      },
      required: ['dataSummary'],
    },
  },
);

const writeSummary = tool(
  async (args: { findings: string }) => {
    return { summary: `Report: ${args.findings.slice(0, 100)}`, word_count: 150 };
  },
  {
    name: 'write_summary',
    description: 'Write a summary report.',
    inputSchema: {
      type: 'object',
      properties: {
        findings: { type: 'string', description: 'The findings to summarize' },
      },
      required: ['findings'],
    },
  },
);

// -- Agents ------------------------------------------------------------------

export const dataCollector = new Agent({
  name: 'data_collector_46',
  model: llmModel,
  instructions: 'Collect data using collect_data. Then transfer to the analyst.',
  tools: [collectData],
});

export const analyst = new Agent({
  name: 'analyst_46',
  model: llmModel,
  instructions: 'Analyze data using analyze_data. Transfer to summarizer when done.',
  tools: [analyzeData],
});

export const summarizer = new Agent({
  name: 'summarizer_46',
  model: llmModel,
  instructions: 'Write a summary using write_summary.',
  tools: [writeSummary],
});

// Coordinator with constrained transitions:
// - data_collector can only go to analyst (not back to coordinator or peers)
// - analyst can go to summarizer or coordinator
// - summarizer can only return to coordinator
export const coordinator = new Agent({
  name: 'coordinator_46',
  model: llmModel,
  instructions:
    'You coordinate a data pipeline. Route to data_collector_46 first, ' +
    'then analyst_46, then summarizer_46.',
  agents: [dataCollector, analyst, summarizer],
  strategy: 'handoff',
  allowedTransitions: {
    data_collector_46: ['analyst_46'],
    analyst_46: ['summarizer_46', 'coordinator_46'],
    summarizer_46: ['coordinator_46'],
  },
});

// -- Run ---------------------------------------------------------------------

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    coordinator,
    'Collect data from the sales database, analyze trends, and write a summary.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(coordinator);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents coordinator_46
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(coordinator);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
