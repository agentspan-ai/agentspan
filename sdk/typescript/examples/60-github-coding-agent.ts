/**
 * 60 - GitHub Coding Agent — pick an issue, code the fix, create a PR.
 *
 * Demonstrates:
 *   - Swarm orchestration with 3 specialist agents + team coordinator
 *   - GitHub integration via gh CLI tools
 *   - Git operations (clone, branch, commit, push)
 *   - Code execution for writing and testing code
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - gh CLI authenticated
 *   - Git configured with push access to the repo
 */

import { z } from 'zod';
import { Agent, AgentRuntime, OnTextMention, tool } from '../src/index.js';
import { execSync } from 'child_process';
import { randomBytes } from 'crypto';
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';

const REPO = 'agentspan/codingexamples';
const WORK_DIR = `/tmp/codingexamples-${randomBytes(4).toString('hex')}`;

// -- GitHub & Git tools ------------------------------------------------------

const listGithubIssues = tool(
  async (args: { state?: string; limit?: number }) => {
    try {
      const result = execSync(
        `gh issue list --repo ${REPO} --state ${args.state ?? 'open'} --limit ${args.limit ?? 10} --json number,title,body,labels`,
        { encoding: 'utf-8', timeout: 30000 },
      );
      return result;
    } catch (e) {
      return `Error listing issues: ${e}`;
    }
  },
  {
    name: 'list_github_issues',
    description: 'List GitHub issues from the repository.',
    inputSchema: z.object({
      state: z.string().optional().describe("Issue state filter -- 'open', 'closed', or 'all'"),
      limit: z.number().optional().describe('Maximum number of issues to return'),
    }),
  },
);

const getGithubIssue = tool(
  async (args: { issueNumber: number }) => {
    try {
      const result = execSync(
        `gh issue view ${args.issueNumber} --repo ${REPO} --json number,title,body,labels,comments`,
        { encoding: 'utf-8', timeout: 30000 },
      );
      return result;
    } catch (e) {
      return `Error getting issue: ${e}`;
    }
  },
  {
    name: 'get_github_issue',
    description: 'Get details of a specific GitHub issue.',
    inputSchema: z.object({
      issueNumber: z.number().describe('The issue number to fetch'),
    }),
  },
);

const cloneRepo = tool(
  async () => {
    try {
      execSync(`gh repo clone ${REPO} ${WORK_DIR}`, {
        encoding: 'utf-8',
        timeout: 60000,
      });
      return `Cloned ${REPO} to ${WORK_DIR}`;
    } catch (e) {
      return `Error cloning: ${e}`;
    }
  },
  {
    name: 'clone_repo',
    description: 'Clone the GitHub repository to a unique /tmp directory.',
    inputSchema: z.object({}),
  },
);

const gitCreateBranch = tool(
  async (args: { branchName: string }) => {
    try {
      execSync(`git checkout -b ${args.branchName}`, {
        encoding: 'utf-8',
        timeout: 10000,
        cwd: WORK_DIR,
      });
      return `Created and checked out branch: ${args.branchName}`;
    } catch (e) {
      return `Error creating branch: ${e}`;
    }
  },
  {
    name: 'git_create_branch',
    description: 'Create and checkout a new git branch.',
    inputSchema: z.object({
      branchName: z.string().describe('Name for the new branch'),
    }),
  },
);

const writeFile = tool(
  async (args: { path: string; content: string }) => {
    const fullPath = join(WORK_DIR, args.path);
    mkdirSync(dirname(fullPath), { recursive: true });
    writeFileSync(fullPath, args.content);
    return `Wrote ${args.content.length} bytes to ${args.path}`;
  },
  {
    name: 'write_file',
    description: 'Write content to a file in the cloned repo.',
    inputSchema: z.object({
      path: z.string().describe("Relative path within the repo (e.g. 'src/utils.py')"),
      content: z.string().describe('The file content to write'),
    }),
  },
);

const readFile = tool(
  async (args: { path: string }) => {
    const fullPath = join(WORK_DIR, args.path);
    if (!existsSync(fullPath)) return `File not found: ${args.path}`;
    return readFileSync(fullPath, 'utf-8');
  },
  {
    name: 'read_file',
    description: 'Read a file from the cloned repo.',
    inputSchema: z.object({
      path: z.string().describe("Relative path within the repo (e.g. 'src/utils.py')"),
    }),
  },
);

const listFiles = tool(
  async (args: { path?: string }) => {
    const fullPath = join(WORK_DIR, args.path ?? '.');
    try {
      const result = execSync('find . -type f -not -path "./.git/*"', {
        encoding: 'utf-8',
        timeout: 10000,
        cwd: fullPath,
      });
      return result || 'Empty directory';
    } catch {
      return `Not a directory: ${args.path}`;
    }
  },
  {
    name: 'list_files',
    description: 'List files in a directory of the cloned repo.',
    inputSchema: z.object({
      path: z.string().optional().describe('Relative directory path (default: repo root)'),
    }),
  },
);

const gitCommitAndPush = tool(
  async (args: { message: string }) => {
    try {
      execSync('git add -A', { cwd: WORK_DIR, timeout: 10000 });
      execSync(`git commit -m "${args.message}"`, { cwd: WORK_DIR, timeout: 10000 });
      execSync('git push -u origin HEAD', { cwd: WORK_DIR, timeout: 30000 });
      return `Committed and pushed: ${args.message}`;
    } catch (e) {
      return `Error: ${e}`;
    }
  },
  {
    name: 'git_commit_and_push',
    description: 'Stage all changes, commit, and push to the remote.',
    inputSchema: z.object({
      message: z.string().describe('The commit message'),
    }),
  },
);

const createPullRequest = tool(
  async (args: { title: string; body: string; issueNumber?: number }) => {
    let body = args.body;
    if (args.issueNumber && args.issueNumber > 0) {
      body = `${body}\n\nCloses #${args.issueNumber}`;
    }
    try {
      const result = execSync(
        `gh pr create --repo ${REPO} --title "${args.title}" --body "${body}"`,
        { encoding: 'utf-8', timeout: 30000, cwd: WORK_DIR },
      );
      return result.trim();
    } catch (e) {
      return `Error creating PR: ${e}`;
    }
  },
  {
    name: 'create_pull_request',
    description: 'Create a GitHub pull request.',
    inputSchema: z.object({
      title: z.string().describe('PR title'),
      body: z.string().describe('PR description/body in markdown'),
      issueNumber: z.number().optional().describe('Issue number to link (0 to skip)'),
    }),
  },
);

// -- Tool sets per agent -----------------------------------------------------

const githubTools = [
  listGithubIssues, getGithubIssue, cloneRepo,
  gitCreateBranch, gitCommitAndPush, createPullRequest,
];
const codingTools = [writeFile, readFile, listFiles];
const qaTools = [readFile, listFiles];

// -- GitHub Agent ------------------------------------------------------------

export const githubAgent = new Agent({
  name: 'github_agent',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a GitHub operations specialist. You handle all git and GitHub CLI interactions.\n\n' +
    'IMPORTANT: Read the conversation history carefully. If the conversation already contains ' +
    'messages from [coder] and [qa_tester] (especially \'ALL TESTS PASSED\' or similar), then ' +
    'the code is already implemented and tested -- you are in PHASE 2. Skip directly to step 6.\n\n' +
    'PHASE 1 -- SETUP:\n' +
    '1. Use list_github_issues to see open issues\n' +
    '2. Use get_github_issue to read the full details\n' +
    '3. Use clone_repo to clone the repository\n' +
    '4. Use git_create_branch to create a feature branch\n' +
    '5. Call transfer_to_coder with the issue details.\n\n' +
    'PHASE 2 -- PR CREATION:\n' +
    '6. Use git_commit_and_push to commit and push the changes\n' +
    '7. Use create_pull_request to create the PR\n' +
    '8. Output the PR URL as your final response.',
  tools: githubTools,
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- Coder -------------------------------------------------------------------

export const coderAgent = new Agent({
  name: 'coder',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are an expert developer. Write clean, well-structured code.\n\n' +
    'WHEN YOU RECEIVE A TASK:\n' +
    '1. Use list_files to understand the repo structure\n' +
    '2. Write your code using write_file\n' +
    '3. Execute your code to verify it works\n' +
    '4. Call transfer_to_qa_tester for review\n\n' +
    'IMPORTANT: You can ONLY use transfer_to_qa_tester. ' +
    `The repo is cloned to ${WORK_DIR}.`,
  tools: codingTools,
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- QA Tester ---------------------------------------------------------------

export const qaTester = new Agent({
  name: 'qa_tester',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a meticulous QA engineer. Review the code written by the coder.\n\n' +
    '1. Use read_file to read the code that was written\n' +
    '2. Execute test cases covering: normal inputs, edge cases, and boundary conditions\n' +
    '3. If you find ANY bugs: call transfer_to_coder.\n' +
    '4. If ALL tests pass: call transfer_to_github_agent.\n\n' +
    'TRANSFER RULES:\n' +
    '  bugs found -> transfer_to_coder\n' +
    '  all tests pass -> transfer_to_github_agent',
  tools: qaTools,
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- Coding Team: swarm coordinator ------------------------------------------

export const codingTeam = new Agent({
  name: 'coding_team',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a coding team coordinator. Delegate the incoming request ' +
    'to github_agent to get started. Call transfer_to_github_agent now.',
  agents: [githubAgent, coderAgent, qaTester],
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
    await runtime.deploy(codingTeam);
    await runtime.serve(codingTeam);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // console.log('='.repeat(60));
    // console.log('  GitHub Coding Agent + QA Tester');
    // console.log(`  Repo: ${REPO}`);
    // console.log(`  Work dir: ${WORK_DIR}`);
    // console.log('  coding_team -> github_agent <-> coder <-> qa_tester (swarm)');
    // console.log('='.repeat(60));
    // console.log(`\nPrompt: ${prompt}\n`);
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(codingTeam, prompt);

    // const output = result.output;
    // const skipKeys = new Set(['finishReason', 'rejectionReason', 'is_transfer', 'transfer_to']);
    // if (output && typeof output === 'object' && !Array.isArray(output)) {
    // for (const [key, text] of Object.entries(output as Record<string, string>)) {
    // if (skipKeys.has(key) || !text) continue;
    // console.log(`\n${'─'.repeat(60)}`);
    // console.log(`  [${key}]`);
    // console.log('─'.repeat(60));
    // console.log(text);
    // }
    // } else {
    // console.log(output);
    // }

    // console.log(`\nFinish reason: ${result.finishReason}`);
    // console.log(`Workflow ID: ${result.workflowId}`);
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('60-github-coding-agent.ts') || process.argv[1]?.endsWith('60-github-coding-agent.js')) {
  main().catch(console.error);
}
