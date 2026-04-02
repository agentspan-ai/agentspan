/**
 * Data Pipeline -- StateGraph with load -> clean -> analyze -> report nodes.
 *
 * Demonstrates:
 *   - A multi-step ETL-style pipeline modelled as a StateGraph
 *   - Each node transforms the state as data flows through
 *   - Using an LLM at the analysis and reporting stages
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const PipelineState = Annotation.Root({
  dataset_name: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  raw_data: Annotation<Record<string, any>[]>({
    reducer: (_prev: Record<string, any>[], next: Record<string, any>[]) => next ?? _prev,
    default: () => [],
  }),
  clean_data: Annotation<Record<string, any>[]>({
    reducer: (_prev: Record<string, any>[], next: Record<string, any>[]) => next ?? _prev,
    default: () => [],
  }),
  analysis: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  report: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof PipelineState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function loadData(state: State): Partial<State> {
  const mockDatasets: Record<string, Record<string, any>[]> = {
    sales: [
      { product: 'Widget A', revenue: 15000, units: 300, region: 'North' },
      { product: 'Widget B', revenue: null, units: 150, region: 'South' },
      { product: 'Widget C', revenue: 8000, units: -5, region: 'East' },
      { product: 'Widget D', revenue: 22000, units: 440, region: 'West' },
      { product: 'Widget E', revenue: 0, units: 0, region: 'North' },
    ],
    users: [
      { id: 1, name: 'Alice', age: 28, active: true },
      { id: 2, name: '', age: -1, active: false },
      { id: 3, name: 'Bob', age: 34, active: true },
    ],
  };
  const dataset =
    mockDatasets[state.dataset_name.toLowerCase()] ?? mockDatasets['sales'];
  return { raw_data: dataset };
}

function cleanData(state: State): Partial<State> {
  const cleaned: Record<string, any>[] = [];
  for (const row of state.raw_data) {
    // Skip rows with null revenue or negative units
    if (row.revenue === null || row.revenue === undefined || (row.units ?? 0) < 0) {
      continue;
    }
    // Remove zero-revenue, zero-unit rows
    if ((row.revenue ?? 0) === 0 && (row.units ?? 0) === 0) {
      continue;
    }
    cleaned.push(row);
  }
  return { clean_data: cleaned };
}

async function analyzeData(state: State): Promise<Partial<State>> {
  const dataStr = state.clean_data.map((row) => JSON.stringify(row)).join('\n');
  const response = await llm.invoke([
    new SystemMessage(
      'You are a data analyst. Analyze the following dataset records and provide: ' +
        '1) Key statistics (totals, averages, ranges), ' +
        '2) Notable patterns or outliers, ' +
        '3) Business insights. Be concise.',
    ),
    new HumanMessage(`Dataset: ${state.dataset_name}\n\n${dataStr}`),
  ]);
  return { analysis: response.content as string };
}

async function generateReport(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a business report writer. ' +
        'Turn the following data analysis into a concise executive summary report ' +
        'with an introduction, key findings, and recommendations.',
    ),
    new HumanMessage(state.analysis),
  ]);
  return { report: response.content as string };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(PipelineState);
builder.addNode('load', loadData);
builder.addNode('clean', cleanData);
builder.addNode('analyze', analyzeData);
builder.addNode('report_node', generateReport);

builder.addEdge(START, 'load');
builder.addEdge('load', 'clean');
builder.addEdge('clean', 'analyze');
builder.addEdge('analyze', 'report_node');
builder.addEdge('report_node', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'sales';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents data_pipeline
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('15-data-pipeline.ts') || process.argv[1]?.endsWith('15-data-pipeline.js')) {
  main().catch(console.error);
}
