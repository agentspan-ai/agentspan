/**
 * 67 - Router to Sequential — route to a pipeline sub-agent.
 *
 * A router selects between a single agent (quick answers) and a
 * sequential pipeline (research tasks requiring multiple stages).
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Quick answer (single agent) ---------------------------------------------

export const quickAnswer = new Agent({
  name: 'quick_answer_67',
  model: llmModel,
  instructions: 'You give quick, 1-2 sentence answers to simple questions.',
});

// -- Research pipeline (sequential) ------------------------------------------

export const researcher = new Agent({
  name: 'researcher_67',
  model: llmModel,
  instructions:
    'You are a researcher. Research the topic and provide 3-5 key ' +
    'facts with supporting details.',
});

export const writer = new Agent({
  name: 'writer_67',
  model: llmModel,
  instructions:
    'You are a writer. Take the research findings and write a clear, ' +
    'engaging summary. Use headers and bullet points.',
});

export const researchPipeline = new Agent({
  name: 'research_pipeline_67',
  model: llmModel,
  agents: [researcher, writer],
  strategy: 'sequential',
});

// -- Router agent ------------------------------------------------------------

export const selector = new Agent({
  name: 'selector_67',
  model: llmModel,
  instructions:
    'You are a request classifier. Select the right team member:\n' +
    '- quick_answer_67: for simple factual questions with short answers\n' +
    '- research_pipeline_67: for research tasks requiring analysis and writing',
});

// -- Team with router --------------------------------------------------------

export const team = new Agent({
  name: 'team_67',
  model: llmModel,
  agents: [quickAnswer, researchPipeline],
  strategy: 'router',
  router: selector,
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(team);
    // await runtime.serve(team);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    // Scenario 1: Research task (routes to pipeline)
    console.log('='.repeat(60));
    console.log('  Scenario 1: Research task (router -> sequential pipeline)');
    console.log('='.repeat(60));
    const result = await runtime.run(
    team,
    'Research the current state of quantum computing and write a summary.',
    );
    result.printResult();

    if (result.status === 'COMPLETED') {
    console.log('[OK] Router -> sequential pipeline completed');
    } else {
    console.log(`[WARN] Unexpected status: ${result.status}`);
    }

    // Scenario 2: Quick question (routes to single agent)
    console.log('\n' + '='.repeat(60));
    console.log('  Scenario 2: Quick question (router -> single agent)');
    console.log('='.repeat(60));
    const result2 = await runtime.run(
    team,
    'What is the capital of France?',
    );
    result2.printResult();

    if (result2.status === 'COMPLETED') {
    console.log('[OK] Router -> quick answer completed');
    } else {
    console.log(`[WARN] Unexpected status: ${result2.status}`);
    }
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('67-router-to-sequential.ts') || process.argv[1]?.endsWith('67-router-to-sequential.js')) {
  main().catch(console.error);
}
