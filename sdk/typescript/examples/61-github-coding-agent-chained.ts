/**
 * 61 - GitHub Coding Agent (Chained) — issue to PR pipeline.
 *
 * Deploys and serves a three-stage pipeline:
 *   1. Fetch open issue, create branch (CLI tools: gh, git)
 *   2. Code fix + QA review (SWARM: coder <-> qa_tester)
 *   3. Create pull request (CLI tool: gh)
 *
 * Requirements:
 *   - Agentspan server running
 *   - GITHUB_TOKEN stored: agentspan credentials set GITHUB_TOKEN <your-github-token>
 *   - gh CLI installed
 */

import { Agent, AgentRuntime, OnTextMention, TextGate } from '@agentspan-ai/sdk';

const REPO = 'agentspan-ai/codingexamples';
const MODEL = 'anthropic/claude-sonnet-4-6';

// -- Stage 1: Fetch issues ---------------------------------------------------

/** Stop when the agent has produced the structured output with issue details. */
function fetchDone(messages: unknown[]): boolean {
  const last = String(messages[messages.length - 1] ?? '');
  return ['REPO:', 'BRANCH:', 'ISSUE:', 'AUTHOR:', 'DETAILS:'].every(tag => last.includes(tag));
}

export const gitFetchIssues = new Agent({
  name: 'git_fetch_issues',
  model: MODEL,
  maxTokens: 8192,
  instructions:
    `You fetch ONE open issue from ${REPO} and push an empty branch.\n\n` +
    `Step 1 — list open issues:\n` +
    `  gh issue list --repo ${REPO} --state open --limit 5\n` +
    `If no issues, respond: NO_OPEN_ISSUES\n\n` +
    `Step 2 — pick an issue and fetch its FULL details (body, author, labels):\n` +
    `  gh issue view <N> --repo ${REPO} --json number,title,body,author,labels\n\n` +
    `You MUST run this command — gh issue list only returns titles, not the issue body.\n` +
    `Read the JSON output carefully and extract the author login and the COMPLETE body text.\n\n` +
    `Step 3 — create a branch and push it (one compound command, shell=true):\n` +
    `  TMPDIR=$(mktemp -d) && gh repo clone ${REPO} "$TMPDIR" && cd "$TMPDIR" && git checkout -b fix/issue-<N> && git push -u origin fix/issue-<N> && echo "DONE"\n\n` +
    `Step 4 — respond with ONLY these lines (NO tool calls):\n` +
    `  REPO: ${REPO}\n` +
    `  BRANCH: fix/issue-<N>\n` +
    `  ISSUE: #<N> <title>\n` +
    `  AUTHOR: <who opened the issue>\n` +
    `  DETAILS: <full issue body — preserve all requirements, acceptance criteria, and context>\n` +
    `  SUMMARY: <one-sentence description>\n\n` +
    `RULES:\n` +
    `- Do NOT create files, commits, or pull requests.\n` +
    `- After step 3, you MUST stop using tools entirely. Just output text.\n` +
    `- Include the COMPLETE issue body in DETAILS — the next stage needs it to implement the fix.`,
  cliConfig: { enabled: true, allowedCommands: ['gh', 'git', 'mktemp', 'ls'], allowShell: true, timeout: 60 },
  credentials: ['GITHUB_TOKEN', 'GH_TOKEN'],
  maxTurns: 20,
  stopWhen: fetchDone,
  gate: new TextGate({ text: 'NO_OPEN_ISSUES' }),
});

// -- Stage 2: Coding + QA (SWARM) -------------------------------------------

export const coderStage = new Agent({
  name: 'coder',
  model: MODEL,
  maxTokens: 60000,
  credentials: ['GITHUB_TOKEN', 'GH_TOKEN'],
  instructions:
    'You are a senior developer. Your input contains issue details from the previous stage\n' +
    'including REPO, BRANCH, ISSUE, AUTHOR, DETAILS, and SUMMARY.\n\n' +
    '1. Read the DETAILS field carefully — it contains the full issue body with requirements.\n' +
    '2. Clone the repo: gh repo clone <REPO> /tmp/work && cd /tmp/work\n' +
    '3. Check out the branch: git checkout <BRANCH>\n' +
    '4. Implement the fix according to ALL requirements in DETAILS.\n' +
    '5. Commit and push your changes.\n' +
    '6. Say HANDOFF_TO_QA with REPO, BRANCH, and a summary of CHANGES.',
  cliConfig: { enabled: true, allowedCommands: ['gh', 'git', 'mktemp', 'rm', 'ls', 'cat', 'mkdir', 'cp'], allowShell: true, timeout: 120 },
});

export const qaStage = new Agent({
  name: 'qa_tester',
  model: MODEL,
  credentials: ['GITHUB_TOKEN', 'GH_TOKEN'],
  instructions:
    'You are a QA engineer. Clone the repo, review changes, run tests.\n' +
    'If bugs found: say HANDOFF_TO_CODER with what to fix.\n' +
    'If good: say QA_APPROVED with REPO/BRANCH/SUMMARY.',
  cliConfig: { enabled: true, allowedCommands: ['gh', 'git', 'mktemp', 'rm', 'ls', 'cat'], allowShell: true, timeout: 120 },
  maxTokens: 60000,
  maxTurns: 15,
});

export const codingQA = new Agent({
  name: 'coding_qa',
  model: MODEL,
  instructions:
    'Delegate to coder, then qa_tester. Loop until QA approves. ' +
    'Output REPO/BRANCH/SUMMARY when done.',
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

/** Stop when the agent has output a PR URL. */
function prDone(messages: unknown[]): boolean {
  const last = String(messages[messages.length - 1] ?? '');
  return last.includes('github.com') && last.includes('/pull/');
}

export const gitPushPR = new Agent({
  name: 'git_push_pr',
  model: MODEL,
  maxTokens: 8192,
  maxTurns: 15,
  credentials: ['GITHUB_TOKEN', 'GH_TOKEN'],
  instructions:
    'Create a pull request. Extract REPO, BRANCH, and ISSUE from the previous stage output.\n\n' +
    'Run this command (shell=true so quotes are handled correctly):\n' +
    '  gh pr create --repo <REPO> --base main --head <BRANCH> --title "Fix <ISSUE>" --body "Fixes <ISSUE>"\n\n' +
    'After the command succeeds, STOP calling tools and respond with ONLY the PR URL.',
  cliConfig: { enabled: true, allowedCommands: ['gh', 'git'], allowShell: true, timeout: 60 },
  stopWhen: prDone,
});

// -- Pipeline ----------------------------------------------------------------

const pipeline = gitFetchIssues.pipe(codingQA).pipe(gitPushPR);

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      pipeline,
      'Pick an open issue and create a PR.',
      { timeoutSeconds: 2400 },
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
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
