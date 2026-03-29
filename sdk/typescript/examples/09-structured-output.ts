/**
 * 09 - Structured Output
 *
 * Demonstrates using a Zod schema as outputType
 * so the agent returns typed structured data.
 */

import { z } from 'zod';
import { Agent, AgentRuntime } from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Define a Zod schema for the expected output --
const ArticleAnalysis = z.object({
  title: z.string().describe('Article title'),
  summary: z.string().describe('Brief summary (1-2 sentences)'),
  category: z.enum(['tech', 'business', 'science', 'creative']).describe('Article category'),
  sentiment: z.enum(['positive', 'neutral', 'negative']).describe('Overall sentiment'),
  keyTopics: z.array(z.string()).describe('Key topics covered'),
  wordCount: z.number().describe('Estimated word count'),
}).describe('ArticleAnalysis');

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
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(analyzerAgent);
    await runtime.serve(analyzerAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // analyzerAgent,
    // 'Analyze: "Quantum Computing Breakthrough: New Error Correction Method Achieves 99.9% Fidelity"',
    // );

    // result.printResult();

    // The output conforms to the ArticleAnalysis schema
    // console.log('\nStructured output:');
    // console.log('  Title:', result.output['title']);
    // console.log('  Category:', result.output['category']);
    // console.log('  Sentiment:', result.output['sentiment']);
    // console.log('  Key Topics:', result.output['keyTopics']);

    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('09-structured-output.ts') || process.argv[1]?.endsWith('09-structured-output.js')) {

  main().catch(console.error);
}
