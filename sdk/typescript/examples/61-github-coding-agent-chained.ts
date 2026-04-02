/**
 * 61 - GitHub Coding Agent (Chained) — conditional sequential pipeline.
 *
 * Demonstrates:
 *   - Sequential pipeline with gate (conditional execution)
 *   - SWARM orchestration nested inside a pipeline stage
 *   - cliCommands for stages that only run CLI tools
 *   - localCodeExecution for stages that write/run code
 *
 * Architecture:
 *   pipeline = gitFetchIssues >> codingQA >> gitPushPR
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - gh CLI authenticated
 */

import { Agent, AgentRuntime, OnTextMention, TextGate } from '../src/index.js';

const REPO = 'agentspan/codingexamples';
const MODEL = 'anthropic/claude-sonnet-4-6';

// -- Stage 1: Fetch issues ---------------------------------------------------

export const gitFetchIssues = new Agent({
  name: 'git_fetch_issues',
  model: MODEL,
  instructions:
    `You are a GitHub issue fetcher. Your ONLY job is to pick an issue and ` +
    `prepare a branch. Do NOT write any code or attempt to fix the issue — ` +
    `the next pipeline stage handles implementation.\n\n` +
    `1. List the 5 most recent open issues on ${REPO} (include number, title, body).\n` +
    `2. If there are NO open issues, output exactly: NO_OPEN_ISSUES\n` +
    `3. Otherwise pick the most suitable issue, then:\n` +
    `   - Create a temp dir: mktemp -d /tmp/fetch-XXXXXXXX\n` +
    `   - Clone ${REPO} into that dir\n` +
    `   - Create branch fix/issue-<NUMBER>\n` +
    `   - Push the empty branch: git push -u origin fix/issue-<NUMBER>\n` +
    `   - Delete the temp dir\n` +
    `   - Output ONLY these lines:\n` +
    `       REPO: ${REPO}\n` +
    `       BRANCH: fix/issue-<NUMBER>\n` +
    `       ISSUE: #<NUMBER> <title>\n` +
    `       SUMMARY: <one-sentence description of the issue>`,
  cliConfig: { enabled: true, allowedCommands: ['gh', 'git', 'mktemp', 'rm'] },
  maxTurns: 20,
  gate: new TextGate({ text: 'NO_OPEN_ISSUES' }),
});

// -- Stage 2: Coding + QA (SWARM) -------------------------------------------

export const coderStage = new Agent({
  name: 'coder',
  model: MODEL,
  maxTokens: 60000,
  instructions:
    'You are a senior developer. Your task description contains REPO, BRANCH, ISSUE, and SUMMARY.\n\n' +
    '1. Create a fresh temp dir: mktemp -d /tmp/coder-XXXXXXXX\n' +
    '2. Clone the repo and check out the branch\n' +
    '3. Implement the fix described in ISSUE/SUMMARY\n' +
    '4. Commit your changes with a descriptive message\n' +
    '5. Push: git push origin <BRANCH>\n' +
    '6. Delete the temp dir\n' +
    '7. Say HANDOFF_TO_QA followed by REPO/BRANCH/CHANGES lines',
  codeExecutionConfig: { enabled: true },
});

export const qaStage = new Agent({
  name: 'qa_tester',
  model: MODEL,
  instructions:
    'You are a QA engineer. Your task description contains REPO, BRANCH, and CHANGES.\n\n' +
    '1. Create a fresh temp dir and clone the repo/branch\n' +
    '2. Review the changed files and run tests\n' +
    '3. Delete the temp dir\n' +
    '4. If bugs: say HANDOFF_TO_CODER with details\n' +
    '5. If good: say QA_APPROVED followed by REPO/BRANCH/SUMMARY lines',
  codeExecutionConfig: { enabled: true },
  maxTokens: 60000,
  maxTurns: 5,
});

export const codingQA = new Agent({
  name: 'coding_qa',
  model: MODEL,
  instructions:
    'Your task description contains REPO, BRANCH, ISSUE, and SUMMARY. ' +
    'Delegate to coder to implement the fix, passing REPO, BRANCH, and the task details. ' +
    'Once coder completes, delegate to qa_tester. ' +
    'If QA does not pass, send it back to coder to fix. ' +
    'When QA approves, output ONLY these lines:\n' +
    '  REPO: <repo>\n' +
    '  BRANCH: <branch>\n' +
    '  SUMMARY: <what was implemented and verified>',
  agents: [coderStage, qaStage],
  strategy: 'swarm',
  handoffs: [
    new OnTextMention({ text: 'HANDOFF_TO_QA', target: 'qa_tester' }),
    new OnTextMention({ text: 'HANDOFF_TO_CODER', target: 'coder' }),
  ],
  maxTurns: 200,
  maxTokens: 60000,
  timeoutSeconds: 6000,
});

// -- Stage 3: Create PR ------------------------------------------------------

export const gitPushPR = new Agent({
  name: 'git_push_pr',
  model: MODEL,
  instructions:
    'You are a GitHub PR creator. Your task description contains REPO, BRANCH, and SUMMARY.\n' +
    'The branch is already pushed -- your only job is to open a pull request.\n\n' +
    '1. Create the PR: gh pr create --repo <REPO> --base main --head <BRANCH> --title "<title>" --body "<summary>"\n' +
    '2. Output the PR URL.',
  cliConfig: { enabled: true, allowedCommands: ['gh', 'git'] },
  maxTokens: 60000,
  maxTurns: 10,
});

// -- Pipeline ----------------------------------------------------------------

const pipeline = gitFetchIssues.pipe(codingQA).pipe(gitPushPR);

// Run the pipeline with streaming

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    pipeline,
    `Pick the most suitable open issue on ${REPO} and implement a fix.`,
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(pipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents git_fetch_issues
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(pipeline);

    // Streaming alternative:
    // console.log('Starting pipeline: gitFetchIssues >> codingQA >> gitPushPR\n');
    // const agentStream = await runtime.stream(
    // pipeline,
    // `Pick the most suitable open issue on ${REPO} and implement a fix.`,
    // );

    // console.log(`Execution: ${agentStream.executionId}\n`);

    // for await (const event of agentStream) {
    // switch (event.type) {
    // case 'thinking':
    // console.log(`  [thinking] ${String(event.content).slice(0, 120)}...`);
    // break;
    // case 'tool_call':
    // console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args).slice(0, 100)})`);
    // break;
    // case 'tool_result':
    // console.log(`  [tool_result] ${event.toolName} -> ${String(event.result).slice(0, 200)}`);
    // break;
    // case 'error':
    // console.log(`  [error] ${event.content}`);
    // break;
    // case 'done':
    // console.log(`\n[done] Pipeline complete.`);
    // console.log(`Output: ${JSON.stringify(event.output).slice(0, 500)}`);
    // break;
    // default:
    // console.log(`  [${event.type}] ${JSON.stringify(event).slice(0, 150)}`);
    // }
    // }

    // const result = await agentStream.getResult();
    // console.log(`\nStatus: ${result.status}`);
    // console.log(`Tool calls: ${result.toolCalls.length}`);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('61-github-coding-agent-chained.ts') || process.argv[1]?.endsWith('61-github-coding-agent-chained.js')) {
  main().catch(console.error);
}
