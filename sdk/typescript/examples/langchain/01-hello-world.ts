/**
 * Hello World -- simplest LangChain chain with no tools.
 *
 * Demonstrates:
 *   - Creating a real ChatOpenAI model with ChatPromptTemplate
 *   - Piping prompt -> model -> StringOutputParser into a RunnableSequence
 *   - Running the chain via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { ChatPromptTemplate } from '@langchain/core/prompts';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { AgentRuntime } from '../../src/index.js';

async function main() {
  // ── Build a real LangChain chain ─────────────────────────
  const model = new ChatOpenAI({
    modelName: 'gpt-4o-mini',
    temperature: 0.7,
  });

  const prompt = ChatPromptTemplate.fromMessages([
    ['system', 'You are a friendly, concise AI assistant. Keep answers under 3 sentences.'],
    ['human', '{input}'],
  ]);

  const chain = prompt.pipe(model).pipe(new StringOutputParser());

  // Add agentspan metadata for extraction
  (chain as any)._agentspan = {
    model: 'openai/gpt-4o-mini',
    tools: [],
    framework: 'langchain',
  };

  const userPrompt = 'Introduce yourself and tell me one interesting fact about large language models.';

  // ── Run on agentspan ──────────────────────────────────────
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(chain, userPrompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
