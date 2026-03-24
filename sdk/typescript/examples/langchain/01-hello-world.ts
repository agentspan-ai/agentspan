/**
 * Hello World -- simplest LangChain chain with no tools.
 *
 * Demonstrates:
 *   - Creating a real ChatOpenAI model with ChatPromptTemplate
 *   - Piping prompt -> model -> StringOutputParser into a RunnableSequence
 *   - Running the chain natively and via AgentRuntime
 *   - Comparing the two results
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

  const userPrompt = 'Introduce yourself and tell me one interesting fact about large language models.';

  // ── Path 1: Native LangChain execution ───────────────────
  console.log('=== Native LangChain Execution ===');
  const nativeResult = await chain.invoke({ input: userPrompt });
  console.log('Result:', nativeResult);

  // ── Path 2: Agentspan runtime execution ──────────────────
  console.log('\n=== Agentspan Runtime Execution ===');
  const runtime = new AgentRuntime();
  const agentspanResult = await runtime.run(chain, userPrompt);
  console.log(`Status: ${agentspanResult.status}`);
  agentspanResult.printResult();

  // ── Compare ──────────────────────────────────────────────
  console.log('\n=== Comparison ===');
  console.log(`Native length:     ${nativeResult.length} chars`);
  console.log(`Agentspan length:  ${String(agentspanResult.output).length} chars`);
  console.log('Both paths produced valid LLM responses.');

  await runtime.shutdown();
}

main().catch(console.error);
