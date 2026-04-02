/**
 * Skills — Load /dg skill as a durable agent.
 *
 * Demonstrates:
 *   - Loading an agentskills.io skill directory as an Agent
 *   - Sub-agents (gilfoyle, dinesh) as real Conductor SUB_WORKFLOW tasks
 *   - Resource files read on demand via read_skill_file worker
 *   - Full execution DAG visibility with per-sub-agent tracking
 *   - Composing skills with regular agents in a pipeline
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
 *   - /dg skill installed (https://github.com/v1r3n/dinesh-gilfoyle)
 */

import { Agent, AgentRuntime, agentTool, skill } from '../src/index.js';
import { llmModel, secondaryLlmModel } from './settings.js';

// ── Load /dg skill as an Agent ─────────────────────────────────────
const dg = skill('~/.claude/skills/dg', {
  model: llmModel,
  agentModels: {
    gilfoyle: secondaryLlmModel, // Gilfoyle gets the bigger model
    dinesh: llmModel,
  },
});

// ── Example 1: Run standalone ──────────────────────────────────────
async function runStandalone() {
  const runtime = new AgentRuntime();
  try {
    console.log('=== /dg Standalone Review ===\n');

    const result = await runtime.run(
      dg,
      `Review this code:

\`\`\`python
import sqlite3
def get_user(name):
    conn = sqlite3.connect('users.db')
    result = conn.execute(f'SELECT * FROM users WHERE name = "{name}"')
    return result.fetchone()
\`\`\``,
    );
    console.log(`\nExecution ID: ${result.executionId}`);
    console.log(`Status: ${result.status}`);
    console.log(`Tokens: ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();

    if (result.subResults) {
      console.log('\nSub-agent executions:');
      for (const [agentName, subResult] of Object.entries(result.subResults)) {
        console.log(`  - ${agentName}: ${JSON.stringify(subResult)}`);
      }
    }

    // Streaming alternative:
    // const stream = await runtime.stream(dg, prompt);
    // for await (const event of stream) {
    //   console.log(`[${event.type}]`, event.toolName ?? event.content ?? '');
    // }
  } finally {
    await runtime.shutdown();
  }
}

// ── Example 2: Compose with regular agent in pipeline ──────────────
async function runPipeline() {
  const fixer = new Agent({
    name: 'fixer',
    model: secondaryLlmModel,
    instructions:
      'You receive a code review with findings. For each critical or important ' +
      'finding, write the fixed code. Output the corrected code with explanations.',
  });

  // Review first, then fix
  const reviewAndFix = dg.pipe(fixer);

  const runtime = new AgentRuntime();
  try {
    console.log('=== Review → Fix Pipeline ===\n');

    const result = await runtime.run(
      reviewAndFix,
      `Review and fix this code:

\`\`\`python
import os
API_KEY = 'sk-1234567890abcdef'
def fetch(url):
    return os.popen(f'curl {url}').read()
\`\`\``,
    );

    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status: ${result.status}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ── Example 3: Use /dg as a tool on another agent ──────────────────
async function runAsTool() {
  const techLead = new Agent({
    name: 'tech_lead',
    model: secondaryLlmModel,
    instructions:
      'You are a tech lead. When asked to review code, use the dg code review tool. ' +
      'After getting results, summarize key findings and prioritize them.',
    tools: [agentTool(dg, { description: 'Run adversarial Dinesh vs Gilfoyle code review' })],
  });

  const runtime = new AgentRuntime();
  try {
    console.log('=== Tech Lead using /dg as Tool ===\n');

    const result = await runtime.run(
      techLead,
      'Please review the authentication module in our latest PR. ' +
        'The code adds JWT token validation.',
    );

    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status: ${result.status}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ── Main ───────────────────────────────────────────────────────────
async function main() {
  const choice = process.argv[2] ?? 'standalone';
  const examples: Record<string, () => Promise<void>> = {
    standalone: runStandalone,
    pipeline: runPipeline,
    tool: runAsTool,
  };

  if (choice in examples) {
    await examples[choice]();
  } else {
    console.log(`Usage: npx tsx ${process.argv[1]} [${Object.keys(examples).join('/')}]`);
  }
}

if (
  process.argv[1]?.endsWith('30-skills-dg-review.ts') ||
  process.argv[1]?.endsWith('30-skills-dg-review.js')
) {
  main().catch(console.error);
}
