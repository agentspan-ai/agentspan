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

const researcher = new Agent({
  name: 'researcher',
  model: llmModel,
  instructions:
    'You are a researcher. Given a topic, provide key facts and data points. ' +
    'Be thorough but concise. Output raw research findings.',
});

const writer = new Agent({
  name: 'writer',
  model: llmModel,
  instructions:
    'You are a writer. Take research findings and write a clear, engaging ' +
    'article. Use headers and bullet points where appropriate.',
});

const editor = new Agent({
  name: 'editor',
  model: llmModel,
  instructions:
    'You are an editor. Review the article for clarity, grammar, and tone. ' +
    'Make improvements and output the final polished version.',
});

// -- Option 1: Using .pipe() ------------------------------------------------

const pipeline = researcher.pipe(writer).pipe(editor);

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(
    pipeline,
    'The impact of AI agents on software development in 2025',
  );
  result.printResult();
} finally {
  await runtime.shutdown();
}

// -- Option 2: Using strategy parameter (equivalent) -------------------------
//
// const pipeline = new Agent({
//   name: 'content_pipeline',
//   model: llmModel,
//   agents: [researcher, writer, editor],
//   strategy: 'sequential',
// });
// const runtime = new AgentRuntime();
// const result = await runtime.run(pipeline, 'The impact of AI agents on software development in 2025');
