/**
 * Google ADK Agent with Output Key -- state management via outputKey.
 *
 * Demonstrates:
 *   - Using outputKey to store agent responses in session state
 *   - Multiple agents that pass data through shared state
 *   - Sub-agent composition for data analysis pipelines
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - GOOGLE_API_KEY or GOOGLE_GENAI_API_KEY for native path
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool, InMemoryRunner, InMemorySessionService } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const analyzeData = new FunctionTool({
  name: 'analyze_data',
  description: 'Analyze a dataset and return key statistics.',
  parameters: z.object({
    dataset: z.string().describe('Name of the dataset to analyze'),
  }),
  execute: async (args: { dataset: string }) => {
    const datasets: Record<string, Record<string, string>> = {
      sales_q4: {
        total_revenue: '$2.3M',
        growth_rate: '12%',
        top_product: 'Widget Pro',
        avg_order_value: '$156',
      },
      user_engagement: {
        daily_active_users: '45,000',
        avg_session_duration: '8.5 min',
        retention_rate: '72%',
        churn_rate: '5.2%',
      },
    };
    return datasets[args.dataset.toLowerCase()] ?? { error: `Dataset '${args.dataset}' not found` };
  },
});

const generateChartDescription = new FunctionTool({
  name: 'generate_chart_description',
  description: 'Generate a description for a chart visualization.',
  parameters: z.object({
    metric: z.string().describe('The metric being visualized'),
    value: z.string().describe('The current value of the metric'),
  }),
  execute: async (args: { metric: string; value: string }) => ({
    chart_type: args.value.includes('%') ? 'gauge' : 'bar',
    metric: args.metric,
    value: args.value,
    recommendation: `Track ${args.metric} weekly for trend analysis.`,
  }),
});

// ── Specialist agents ────────────────────────────────────────────────

// Analyst agent -- stores its findings in state via outputKey
const analyst = new LlmAgent({
  name: 'data_analyst',
  model,
  instruction:
    'You are a data analyst. Use the analyze_data tool to examine datasets. ' +
    'Provide a clear summary of the key findings.',
  tools: [analyzeData],
  outputKey: 'analysis_results',
});

// Visualizer agent -- reads from state
const visualizer = new LlmAgent({
  name: 'chart_designer',
  model,
  instruction:
    'You are a data visualization expert. Based on the analysis results, ' +
    'suggest appropriate visualizations. Use the generate_chart_description ' +
    'tool for each key metric.',
  tools: [generateChartDescription],
});

// Coordinator delegates to both
const coordinator = new LlmAgent({
  name: 'report_coordinator',
  model,
  instruction:
    'You are a report coordinator. First, have the data analyst examine ' +
    'the requested dataset. Then, have the chart designer suggest ' +
    'visualizations. Provide a final executive summary.',
  subAgents: [analyst, visualizer],
});

// ── Path 1: Native ADK ──────────────────────────────────────────────

async function runNative() {
  console.log('=== Native ADK ===');
  console.log('Coordinator:', coordinator.name);
  console.log('Sub-agents:', coordinator.subAgents.map((a: any) => a.name).join(', '));
  console.log('Analyst outputKey:', analyst.outputKey);

  const sessionService = new InMemorySessionService();
  const runner = new InMemoryRunner({ agent: coordinator, appName: 'output-key', sessionService });
  const session = await sessionService.createSession({ appName: 'output-key', userId: 'user1' });

  const prompt = 'Create a report on the sales_q4 dataset with visualization recommendations.';
  const message = { role: 'user' as const, parts: [{ text: prompt }] };

  try {
    let lastText = '';
    for await (const event of runner.runAsync({
      userId: 'user1',
      sessionId: session.id,
      newMessage: message,
    })) {
      const parts = event?.content?.parts;
      if (Array.isArray(parts)) {
        for (const part of parts) {
          if (typeof part?.text === 'string') lastText = part.text;
        }
      }
    }
    console.log('Response:', lastText?.slice(0, 500) || '(no response)');
  } catch (err: any) {
    console.log('Native path error (expected without GOOGLE_API_KEY):', err.message?.slice(0, 200));
  }
}

// ── Path 2: Agentspan ───────────────────────────────────────────────

async function runAgentspan() {
  console.log('\n=== Agentspan ===');
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      coordinator,
      'Create a report on the sales_q4 dataset with visualization recommendations.',
    );
    console.log(`Status: ${result.status}`);
    result.printResult();
  } catch (err: any) {
    console.log('Agentspan path error:', err.message?.slice(0, 200));
  } finally {
    await runtime.shutdown();
  }
}

// ── Run ──────────────────────────────────────────────────────────────

async function main() {
  await runNative();
  await runAgentspan();
}

main().catch(console.error);
