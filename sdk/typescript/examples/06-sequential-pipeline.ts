/**
 * Sequential Pipeline — Agent.pipe(Agent).pipe(Agent)
 *
 * Demonstrates the sequential strategy where agents run in order and the
 * output of each agent becomes the input of the next.
 *
 * Also shows the .pipe() method shorthand.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Pipeline agents ---------------------------------------------------------

export const researcher = new Agent({
  name: 'researcher',
  model: llmModel,
  instructions:
    'You are a researcher. Given a topic, provide key facts and data points. ' +
    'Be thorough but concise. Output raw research findings.',
});

export const writer = new Agent({
  name: 'writer',
  model: llmModel,
  instructions:
    'You are a writer. Take research findings and write a clear, engaging ' +
    'article. Use headers and bullet points where appropriate.',
});

export const editor = new Agent({
  name: 'editor',
  model: llmModel,
  instructions:
    'You are an editor. Review the article for clarity, grammar, and tone. ' +
    'Make improvements and output the final polished version.',
});

// -- Option 1: Using .pipe() ------------------------------------------------

const pipeline = researcher.pipe(writer).pipe(editor);

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(pipeline);
    await runtime.serve(pipeline);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // pipeline,
    // 'The impact of AI agents on software development in 2025',
    // );
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }

    // // -- Option 2: Using strategy parameter (equivalent) -------------------------
    // //
    // // const pipeline = new Agent({
    // //   name: 'content_pipeline',
    // //   model: llmModel,
    // //   agents: [researcher, writer, editor],
    // //   strategy: 'sequential',
    // // });
    // // const runtime = new AgentRuntime();
    // // const result = await runtime.run(pipeline, 'The impact of AI agents on software development in 2025');
}

if (process.argv[1]?.endsWith('06-sequential-pipeline.ts') || process.argv[1]?.endsWith('06-sequential-pipeline.js')) {
  main().catch(console.error);
}
