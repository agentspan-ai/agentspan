/**
 * Crash & Resume -- restart workers after a process crash.
 *
 * Demonstrates the production pattern for durable LangGraph execution:
 *   - deploy() registers the workflow definition on the server (one-time)
 *   - start() triggers an execution via the server API
 *   - serve() registers workers and keeps them polling
 *   - After a crash, just restart serve() — the server dispatches stalled
 *     tasks to the new workers and the execution resumes automatically
 *
 * How this works:
 *   Phase 1: Deploy the agent definition, start an execution, and serve
 *   workers briefly. Call shutdown() to simulate a crash — workers die
 *   but the workflow is durable on the server.
 *
 *   Phase 2: Create a fresh AgentRuntime and call serve(graph). This
 *   re-serializes the graph, re-registers the same workers, and starts
 *   polling. The server sees workers available again and dispatches any
 *   stalled tasks. The execution picks up where it left off — no special
 *   resume logic, no execution_id needed.
 *
 * Why this matters:
 *   LangGraph graphs running through Agentspan are compiled into durable
 *   Conductor workflows. If your process crashes (OOM, deploy, exception),
 *   no work is lost — the server holds the workflow state. You just need
 *   to restart serve() and the workers pick up from where they left off.
 *
 * Production pattern:
 *   // CI/CD (once):
 *   await runtime.deploy(graph);
 *
 *   // Long-running worker process (restart on crash):
 *   await runtime.serve(graph);
 *
 *   // Trigger executions from anywhere:
 *   await runtime.start(graph, "prompt");  // or via server API / UI
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
 *   - OPENAI_API_KEY for ChatOpenAI
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '@agentspan-ai/sdk';
import * as fs from 'node:fs';
import * as readline from 'node:readline';

const SESSION_FILE = '/tmp/agentspan_langgraph_resume.session';
const SERVER_URL = process.env.AGENTSPAN_SERVER_URL ?? 'http://localhost:6767/api';
const UI_BASE = SERVER_URL.replace('/api', '');

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function prompt(message: string): Promise<void> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(message, () => {
      rl.close();
      resolve();
    });
  });
}

// -- Tools that simulate real work (each takes several seconds) ----------------

const fetchSalesData = new DynamicStructuredTool({
  name: 'fetch_sales_data',
  description: 'Fetch raw sales data for a given quarter from the data warehouse.',
  schema: z.object({
    quarter: z.string().describe('The quarter to fetch data for, e.g. Q4 2025'),
  }),
  func: async ({ quarter }) => {
    console.log(`  [fetch_sales_data] Querying data warehouse for ${quarter}...`);
    await sleep(3000);
    return (
      `Sales data for ${quarter}: ` +
      'revenue=$12.4M, units=45200, regions=NA/EMEA/APAC, ' +
      'top_product=Widget Pro, growth=+8.3%'
    );
  },
});

const analyzeTrends = new DynamicStructuredTool({
  name: 'analyze_trends',
  description: 'Run trend analysis on sales data to identify patterns and anomalies.',
  schema: z.object({
    data: z.string().describe('The raw sales data to analyze'),
  }),
  func: async ({ data }) => {
    console.log('  [analyze_trends] Running statistical analysis...');
    await sleep(3000);
    return (
      'Trend analysis: Q-over-Q growth accelerating in APAC (+14%), ' +
      'EMEA flat, NA slight decline (-2%). ' +
      'Anomaly: Widget Pro spike in APAC correlates with marketing campaign. ' +
      'Seasonality detected in unit volumes.'
    );
  },
});

const generateReport = new DynamicStructuredTool({
  name: 'generate_report',
  description: 'Generate an executive summary report from the analysis.',
  schema: z.object({
    analysis: z.string().describe('The trend analysis to summarize'),
  }),
  func: async ({ analysis }) => {
    console.log('  [generate_report] Formatting executive report...');
    await sleep(3000);
    return (
      'EXECUTIVE SUMMARY\n' +
      'Revenue: $12.4M (+8.3% YoY)\n' +
      'Key insight: APAC driving growth, recommend increasing investment.\n' +
      'Risk: NA declining — needs attention.\n' +
      'Recommendation: Double APAC marketing budget, investigate NA churn.'
    );
  },
});

// -- Build the LangGraph agent ------------------------------------------------

const tools = [fetchSalesData, analyzeTrends, generateReport];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({ llm, tools, name: 'sales_analyst' });

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const TASK_PROMPT =
  'Fetch the Q4 2025 sales data, run a full trend analysis on it, ' +
  'then generate an executive summary report. ' +
  'Call each tool in sequence — do not skip any step.';

// -- Phase 1: Deploy, start, serve briefly, then crash ------------------------

async function main() {
  console.log('='.repeat(60));
  console.log('Phase 1: Deploy + start, then simulate crash');
  console.log('='.repeat(60));

  const runtime1 = new AgentRuntime();
  try {
    // Deploy the workflow definition (in production, do this once in CI/CD)
    await runtime1.deploy(graph);
    console.log('Agent deployed to server.');

    // Start an execution — registers workers, starts polling, fires execution
    const handle = await runtime1.start(graph, TASK_PROMPT);
    console.log(`Execution started: ${handle.executionId}`);

    // Save execution_id so we can check status later
    fs.writeFileSync(SESSION_FILE, handle.executionId);

    // Let workers run briefly — first tool should start
    console.log('\nServing workers briefly...');
    await sleep(8000);
  } finally {
    // Simulate crash — stop workers
    await runtime1.shutdown();
  }

  console.log('\nRuntime closed — workers are dead, workflow persists on server.');
  console.log();

  const savedExecutionId = fs.readFileSync(SESSION_FILE, 'utf8').trim();

  // -- Pause: let the user see the stalled execution in the UI ----------------

  const uiLink = `${UI_BASE}/execution/${savedExecutionId}`;
  console.log('-'.repeat(60));
  console.log('Open the Agentspan UI to see the execution in RUNNING state:');
  console.log(`  ${uiLink}`);
  console.log();
  console.log('The workflow is alive on the server but stalled — no workers are');
  console.log('polling to pick up the next task.  The completed steps are');
  console.log('preserved; only the remaining steps need to run.');
  console.log('-'.repeat(60));
  await prompt('\nPress Enter to resume (restart workers)...');
  console.log();

  // -- Phase 2: Restart serve — workers pick up stalled tasks -----------------

  console.log('='.repeat(60));
  console.log('Phase 2: Restart serve() — workers reconnect automatically');
  console.log('='.repeat(60));

  const runtime2 = new AgentRuntime();
  try {
    // serve() re-registers the same workers. The server dispatches
    // stalled tasks to them — no resume() call needed.
    console.log('\nServing workers (non-blocking for demo)...');
    void runtime2.serve(graph);  // runs in background, blocks until SIGTERM

    // Give workers a moment to start polling
    await sleep(1000);

    // Poll until the execution completes
    console.log(`Polling execution: ${savedExecutionId}`);
    let status = await runtime2.getStatus(savedExecutionId);
    while (!status.isComplete) {
      await sleep(2000);
      status = await runtime2.getStatus(savedExecutionId);
      console.log(`  status: ${status.status}`);
    }

    console.log(`\nStatus: ${status.status}`);
    console.log(`Output: ${JSON.stringify(status.output, null, 2)}`);
    console.log('\nCheck the completed execution in the UI:');
    console.log(`  ${uiLink}`);
  } finally {
    await runtime2.shutdown();
  }

  console.log('\nDone — same workflow, seamless resume after simulated crash.');
}

main().catch(console.error);
