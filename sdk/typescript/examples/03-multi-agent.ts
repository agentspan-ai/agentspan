/**
 * 03 - Multi-Agent
 *
 * Demonstrates three orchestration strategies:
 * 1. Sequential (.pipe()) — agents run in order
 * 2. Parallel — agents run concurrently
 * 3. Handoff — agents delegate to sub-agents
 */

import {
  Agent,
  AgentRuntime,
  OnTextMention,
} from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// ── Sequential: writer -> editor ─────────────────────────

export const writer = new Agent({
  name: 'writer',
  model: MODEL,
  instructions: 'Write a short paragraph about the given topic.',
});

export const editor = new Agent({
  name: 'editor',
  model: MODEL,
  instructions: 'Edit the text for clarity and brevity.',
});

// .pipe() creates a sequential pipeline
const writingPipeline = writer.pipe(editor);

// ── Parallel: multiple researchers ───────────────────────

export const webResearcher = new Agent({
  name: 'web_researcher',
  model: MODEL,
  instructions: 'Research the topic from web sources.',
});

export const dataAnalyst = new Agent({
  name: 'data_analyst',
  model: MODEL,
  instructions: 'Analyze data trends related to the topic.',
});

export const researchTeam = new Agent({
  name: 'research_team',
  agents: [webResearcher, dataAnalyst],
  strategy: 'parallel',
});

// ── Handoff: router delegates to specialists ────────────

export const pythonExpert = new Agent({
  name: 'python_expert',
  model: MODEL,
  instructions: 'Answer Python programming questions.',
  introduction: 'I specialize in Python.',
});

export const jsExpert = new Agent({
  name: 'js_expert',
  model: MODEL,
  instructions: 'Answer JavaScript programming questions.',
  introduction: 'I specialize in JavaScript.',
});

export const codingTeam = new Agent({
  name: 'coding_team',
  model: MODEL,
  instructions: 'Route to the appropriate language expert.',
  agents: [pythonExpert, jsExpert],
  strategy: 'swarm',
  handoffs: [
    new OnTextMention({ target: 'python_expert', text: 'Python' }),
    new OnTextMention({ target: 'js_expert', text: 'JavaScript' }),
  ],
});

// ── Run examples ─────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(writingPipeline);
    await runtime.serve(writingPipeline);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // console.log('=== Sequential Pipeline ===');
    // const seqResult = await runtime.run(writingPipeline, 'Quantum computing');
    // seqResult.printResult();

    // console.log('\n=== Parallel Research ===');
    // const parResult = await runtime.run(researchTeam, 'AI trends in 2026');
    // parResult.printResult();

    // console.log('\n=== Handoff Team ===');
    // const handoffResult = await runtime.run(
    // codingTeam,
    // 'How do I use async/await in Python?',
    // );
    // handoffResult.printResult();

    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('03-multi-agent.ts') || process.argv[1]?.endsWith('03-multi-agent.js')) {

  main().catch(console.error);
}
