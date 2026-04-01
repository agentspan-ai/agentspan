/**
 * 60a - GitHub Coding Agent (simplified) — pick an issue, code the fix, create a PR.
 *
 * Uses built-in code execution (localCodeExecution: true) so the LLM
 * composes shell commands naturally -- zero custom tool definitions.
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - gh CLI authenticated
 *   - Git configured with push access to the repo
 */

import { Agent, AgentRuntime, OnTextMention } from '../src/index.js';
import { randomBytes } from 'crypto';

const REPO = 'agentspan/codingexamples';
const WORK_DIR = `/tmp/codingexamples-${randomBytes(4).toString('hex')}`;

// -- GitHub Agent ------------------------------------------------------------

export const githubAgent = new Agent({
  name: 'github_agent',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a GitHub operations specialist.\n\n' +
    `Repo: ${REPO}\nWork dir: ${WORK_DIR}\n\n` +
    'IMPORTANT: Read conversation history carefully.\n\n' +
    'PHASE 1 -- SETUP:\n' +
    `1. List issues: gh issue list --repo ${REPO} --state open --json number,title,body\n` +
    '2. Pick the most suitable issue\n' +
    `3. Clone: gh repo clone ${REPO} ${WORK_DIR}\n` +
    `4. Branch: cd ${WORK_DIR} && git checkout -b feature/issue-N-desc\n` +
    '5. Call transfer_to_coder with the issue details.\n\n' +
    'PHASE 2 -- PR CREATION:\n' +
    `6. Commit: cd ${WORK_DIR} && git add -A && git commit -m "Fix #N: desc" && git push -u origin HEAD\n` +
    `7. Create PR: gh pr create --repo ${REPO} --title "Fix #N: title" --body "Description."\n` +
    '8. Output the PR URL. Do NOT call any transfer tool after this.',
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- Coder -------------------------------------------------------------------

export const coder = new Agent({
  name: 'coder',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are an expert developer.\n\n' +
    `The repo is cloned at ${WORK_DIR}.\n\n` +
    'WHEN YOU RECEIVE A TASK:\n' +
    `1. Explore: find ${WORK_DIR} -type f -not -path "*/.git/*"\n` +
    '2. Write ALL files in a SINGLE bash execution using heredocs\n' +
    '3. Test your code to verify it works\n' +
    '4. Call transfer_to_qa_tester for review\n\n' +
    'IMPORTANT: You can ONLY use transfer_to_qa_tester.\n' +
    'Each tool call uses one turn. Minimize turns by combining commands.',
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- QA Tester ---------------------------------------------------------------

export const qaTester = new Agent({
  name: 'qa_tester',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a meticulous QA engineer.\n\n' +
    `The repo is at ${WORK_DIR}. You can read files with:\n  cat ${WORK_DIR}/src/main.py\n\n` +
    'Include ALL necessary code in each execution.\n\n' +
    'TRANSFER RULES:\n' +
    '  bugs found -> call transfer_to_coder\n' +
    '  all tests pass -> call transfer_to_github_agent\n' +
    '  NEVER call transfer_to_coding_team',
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- Coding Team: swarm coordinator ------------------------------------------

export const codingTeam = new Agent({
  name: 'coding_team',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a coding team coordinator. Delegate to github_agent. ' +
    'Call transfer_to_github_agent now.',
  agents: [githubAgent, coder, qaTester],
  strategy: 'swarm',
  handoffs: [
    new OnTextMention({ text: 'transfer_to_github_agent', target: 'github_agent' }),
    new OnTextMention({ text: 'transfer_to_coder', target: 'coder' }),
    new OnTextMention({ text: 'transfer_to_qa_tester', target: 'qa_tester' }),
  ],
  allowedTransitions: {
    coding_team: ['github_agent'],
    github_agent: ['coder'],
    coder: ['qa_tester'],
    qa_tester: ['coder', 'github_agent'],
  },
  maxTurns: 30,
  timeoutSeconds: 900,
});

// -- Run ---------------------------------------------------------------------

const prompt =
  'Pick an open issue from the GitHub repository, implement the ' +
  'feature or fix the bug, get it reviewed by QA, and create a PR.';

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(codingTeam);
    // await runtime.serve(codingTeam);
    // Direct run for local development:
    console.log('='.repeat(60));
    console.log('  GitHub Coding Agent (Simplified)');
    console.log(`  Repo: ${REPO}`);
    console.log(`  Work dir: ${WORK_DIR}`);
    console.log('  coding_team -> github_agent <-> coder <-> qa_tester (swarm)');
    console.log('  Tools: built-in code execution (any language)');
    console.log('='.repeat(60));
    console.log(`\nPrompt: ${prompt}\n`);
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(codingTeam, prompt);

    const output = result.output;
    const skipKeys = new Set(['finishReason', 'rejectionReason', 'is_transfer', 'transfer_to']);
    if (output && typeof output === 'object' && !Array.isArray(output)) {
    for (const [key, text] of Object.entries(output as Record<string, string>)) {
    if (skipKeys.has(key) || !text) continue;
    console.log(`\n${'─'.repeat(60)}`);
    console.log(`  [${key}]`);
    console.log('─'.repeat(60));
    console.log(text);
    }
    } else {
    console.log(output);
    }

    console.log(`\nFinish reason: ${result.finishReason}`);
    console.log(`Execution ID: ${result.executionId}`);
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('60a-github-coding-agent-simple.ts') || process.argv[1]?.endsWith('60a-github-coding-agent-simple.js')) {
  main().catch(console.error);
}
