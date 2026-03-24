/**
 * Prompt Templates -- using ChatPromptTemplate for structured agent prompts.
 *
 * Demonstrates:
 *   - Building ChatPromptTemplate with system + human messages and variables
 *   - Using PromptTemplate for parameterized system prompts (persona, domain, style)
 *   - RunnableSequence with template composition
 *   - DynamicStructuredTool for domain-specific lookup
 *   - Running via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Persona prompt template ──────────────────────────────

function buildSystemPrompt(personaName: string, domain: string, style: string): string {
  return `You are ${personaName}, an expert ${domain} consultant.
Your communication style is ${style}.
Always structure your responses with:
1. A brief direct answer
2. Key supporting details
3. A practical next step

Use the provided tools to look up specific concepts or tool recommendations when asked.`;
}

// ── Domain tools ─────────────────────────────────────────

const explainConceptTool = new DynamicStructuredTool({
  name: 'explain_concept',
  description: 'Explain a data engineering concept. Knows: ETL, data lake, data warehouse, streaming, dbt, airflow.',
  schema: z.object({
    concept: z.string().describe('The concept to explain, e.g. "ETL", "data lake"'),
  }),
  func: async ({ concept }) => {
    const explanations: Record<string, string> = {
      etl: 'Extract, Transform, Load -- a pipeline that pulls data from sources, transforms it, and loads into a target.',
      'data lake': 'A centralized repository storing raw data at any scale in its native format.',
      'data warehouse': 'A structured analytical database optimized for querying and reporting (e.g., BigQuery, Redshift).',
      streaming: 'Real-time data processing as events occur, using tools like Kafka, Flink, or Spark Streaming.',
      dbt: 'Data Build Tool -- SQL-based transformation framework for analytics engineering.',
      airflow: 'Apache Airflow -- workflow orchestration platform for scheduling and monitoring data pipelines.',
    };
    const key = concept.toLowerCase().trim();
    return explanations[key] ?? `No explanation available for "${concept}".`;
  },
});

const recommendToolTool = new DynamicStructuredTool({
  name: 'recommend_tool',
  description: 'Recommend data engineering tools for a given use case. Knows: batch processing, stream processing, orchestration, storage, transformation.',
  schema: z.object({
    useCase: z.string().describe('The use case, e.g. "batch processing", "orchestration"'),
  }),
  func: async ({ useCase }) => {
    const recommendations: Record<string, string> = {
      'batch processing': 'Apache Spark or dbt for large-scale batch transformations.',
      'stream processing': 'Apache Kafka + Flink or AWS Kinesis for real-time streaming.',
      orchestration: 'Apache Airflow, Prefect, or Dagster for workflow scheduling.',
      storage: 'Snowflake or BigQuery for warehousing; S3 or GCS for data lake storage.',
      transformation: 'dbt (SQL) or Spark (Python) for data transformations.',
    };
    const key = useCase.toLowerCase().trim();
    return recommendations[key] ?? `No recommendation available for "${useCase}".`;
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [explainConceptTool, recommendToolTool];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runPersonaAgent(prompt: string): Promise<string> {
  const systemPrompt = buildSystemPrompt('Dr. Data', 'data engineering', 'concise and technical');
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage(systemPrompt),
    new HumanMessage(prompt),
  ];

  for (let i = 0; i < 5; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    for (const tc of toolCalls) {
      const tool = toolMap[tc.name];
      if (tool) {
        const result = await (tool as any).invoke(tc.args);
        messages.push(new ToolMessage({ content: String(result), tool_call_id: tc.id! }));
      }
    }
  }

  return 'Agent reached maximum iterations.';
}

// ── Wrap for Agentspan ───────────────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runPersonaAgent(input.input);
    return { output };
  },
});

// Add agentspan metadata for extraction
(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langchain',
};

async function main() {
  const userPrompt = 'What tool should I use for batch processing, and can you explain ETL?';

  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agentRunnable, userPrompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
