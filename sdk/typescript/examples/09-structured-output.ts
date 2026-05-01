/**
 * 09 - Structured Output
 *
 * Demonstrates using a Zod schema as outputType
 * so the agent returns typed structured data.
 */

import { Agent, AgentRuntime } from '@agentspan-ai/sdk';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Define a Zod schema for the expected output --
const ArticleAnalysis = {
  type: 'object',
  properties: {
    title: { type: 'string', description: 'Article title' },
    summary: { type: 'string', description: 'Brief summary (1-2 sentences)' },
    category: { type: 'string', enum: ['tech', 'business', 'science', 'creative'], description: 'Article category' },
    sentiment: { type: 'string', enum: ['positive', 'neutral', 'negative'], description: 'Overall sentiment' },
    keyTopics: { type: 'array', items: { type: 'string' }, description: 'Key topics covered' },
    wordCount: { type: 'number', description: 'Estimated word count' },
  },
  required: ['title', 'summary', 'category', 'sentiment', 'keyTopics', 'wordCount'],
};

// -- Agent with structured output --
export const analyzerAgent = new Agent({
  name: 'article_analyzer',
  model: MODEL,
  instructions:
    'Analyze the given article topic and return a structured analysis. ' +
    'Provide realistic estimated values.',
  outputType: ArticleAnalysis,
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    analyzerAgent,
    'Analyze: "Quantum Computing Breakthrough: New Error Correction Method Achieves 99.9% Fidelity"',
    );

    result.printResult();

    // The output conforms to the ArticleAnalysis schema
    // result.output is the full server envelope { result: {...}, finishReason, context }.
    // The structured data lives under result.output.result.
    const structured = result.output['result'] as Record<string, unknown>;
    console.log('\nStructured output:');
    console.log('  Title:', structured?.['title']);
    console.log('  Category:', structured?.['category']);
    console.log('  Sentiment:', structured?.['sentiment']);
    console.log('  Key Topics:', structured?.['keyTopics']);

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(analyzerAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents article_analyzer
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(analyzerAgent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
