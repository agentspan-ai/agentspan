/**
 * Credentials -- CLI tools with explicit credential declarations.
 *
 * Demonstrates:
 *   - Explicit credentials on agents and tools
 *   - cliConfig.allowedCommands defines which CLI tools the agent can use
 *   - credentials: [...] declares which secrets the server must inject
 *   - Multi-credential tools (aws needs multiple env vars)
 *
 * Setup (one-time, via CLI):
 *   agentspan login
 *   agentspan credentials set GITHUB_TOKEN <your-github-token>
 *   agentspan credentials set AWS_ACCESS_KEY_ID <your-aws-access-key-id>
 *   agentspan credentials set AWS_SECRET_ACCESS_KEY <your-aws-secret-access-key>
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - gh and aws CLIs installed
 */

import { execSync } from 'node:child_process';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- gh tool: list pull requests ----------------------------------------------

const ghListPrs = tool(
  async (args: { repo: string; state?: string }) => {
    const state = args.state ?? 'open';
    const ghToken = process.env.GITHUB_TOKEN ?? '';
    try {
      const stdout = execSync(
        `gh pr list --repo ${args.repo} --state ${state} --limit 10 --json number,title,author,createdAt,url`,
        {
          timeout: 15_000,
          encoding: 'utf-8',
          env: { ...process.env, GH_TOKEN: ghToken },
        },
      );
      const prs = JSON.parse(stdout);
      return { repo: args.repo, state, pull_requests: prs };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'gh_list_prs',
    description: 'List pull requests for a GitHub repo using the gh CLI. repo format: "owner/repo"',
    inputSchema: {
      type: 'object',
      properties: {
        repo: { type: 'string', description: 'Repository in "owner/repo" format' },
        state: { type: 'string', description: '"open", "closed", or "all"' },
      },
      required: ['repo'],
    },
    credentials: ['GITHUB_TOKEN'],
  },
);

// -- gh tool: create pull request ---------------------------------------------

const ghCreatePr = tool(
  async (args: { repo: string; title: string; body: string; head: string; base?: string }) => {
    const base = args.base ?? 'main';
    const ghToken = process.env.GITHUB_TOKEN ?? '';
    try {
      const stdout = execSync(
        `gh pr create --repo ${args.repo} --title "${args.title}" --body "${args.body}" --head ${args.head} --base ${base}`,
        {
          timeout: 15_000,
          encoding: 'utf-8',
          env: { ...process.env, GH_TOKEN: ghToken },
        },
      );
      return { url: stdout.trim() };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'gh_create_pr',
    description: 'Create a pull request via the gh CLI.',
    inputSchema: {
      type: 'object',
      properties: {
        repo: { type: 'string', description: 'Repository in "owner/repo" format' },
        title: { type: 'string', description: 'PR title' },
        body: { type: 'string', description: 'PR body' },
        head: { type: 'string', description: 'Source branch' },
        base: { type: 'string', description: 'Target branch (default: main)' },
      },
      required: ['repo', 'title', 'body', 'head'],
    },
    credentials: ['GITHUB_TOKEN'],
  },
);

// -- aws tool: list S3 buckets ------------------------------------------------

const awsListS3Buckets = tool(
  async () => {
    try {
      const stdout = execSync('aws s3 ls --output json', {
        timeout: 15_000,
        encoding: 'utf-8',
      });
      const lines = stdout
        .trim()
        .split('\n')
        .filter((l) => l.trim());
      const buckets = lines.map((line) => {
        const parts = line.trim().split(/\s+/);
        return parts.length >= 3
          ? { created: `${parts[0]} ${parts[1]}`, name: parts[2] }
          : { name: line.trim() };
      });
      return { buckets };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'aws_list_s3_buckets',
    description: "List S3 buckets accessible with the user's AWS credentials.",
    inputSchema: { type: 'object', properties: {} },
    credentials: ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN'],
  },
);

// -- aws tool: get caller identity --------------------------------------------

const awsGetCallerIdentity = tool(
  async () => {
    try {
      const stdout = execSync('aws sts get-caller-identity --output json', {
        timeout: 10_000,
        encoding: 'utf-8',
      });
      return JSON.parse(stdout);
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'aws_get_caller_identity',
    description: 'Return the AWS identity (account, ARN) for the current credentials.',
    inputSchema: { type: 'object', properties: {} },
    credentials: ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN'],
  },
);

// -- Agent with CLI allowed commands ------------------------------------------

export const githubAwsAgent = new Agent({
  name: 'devops_agent',
  model: llmModel,
  tools: [ghListPrs, ghCreatePr, awsListS3Buckets, awsGetCallerIdentity],
  cliConfig: { enabled: true, allowedCommands: ['gh', 'aws'] },
  credentials: ['GITHUB_TOKEN', 'GH_TOKEN', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN'],
  instructions:
    'You are a DevOps assistant. You can manage GitHub pull requests and ' +
    'inspect AWS resources. Always confirm destructive actions before proceeding.',
});

// -- Run ----------------------------------------------------------------------

const task = process.argv.slice(2).join(' ') || 'Who am I in AWS, and list my S3 buckets?';

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(githubAwsAgent, task);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(githubAwsAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents devops_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(githubAwsAgent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
