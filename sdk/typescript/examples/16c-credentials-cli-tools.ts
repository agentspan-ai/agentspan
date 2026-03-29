/**
 * Credentials -- CLI tools with automatic credential mapping.
 *
 * Demonstrates:
 *   - cliConfig.allowedCommands auto-maps to credentials (gh -> GITHUB_TOKEN, aws -> AWS_*)
 *   - No need to declare credentials manually when using CLI tools
 *   - Multi-credential tools (aws needs multiple env vars)
 *
 * CLI credential auto-mapping (built-in):
 *   gh          -> GITHUB_TOKEN
 *   aws         -> AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
 *   gcloud      -> GOOGLE_APPLICATION_CREDENTIALS (CredentialFile)
 *   docker      -> DOCKER_USERNAME, DOCKER_PASSWORD
 *   kubectl     -> KUBECONFIG (CredentialFile)
 *   az          -> AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID
 *   npm         -> NPM_TOKEN
 *   pip         -> PIP_INDEX_URL
 *   databricks  -> DATABRICKS_TOKEN, DATABRICKS_HOST
 *   snowflake   -> SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
 *   terraform   -> ConfigurationError (use tool() with explicit credentials)
 *
 * Setup (one-time, via CLI):
 *   agentspan login
 *   agentspan credentials set --name GITHUB_TOKEN
 *   agentspan credentials set --name AWS_ACCESS_KEY_ID
 *   agentspan credentials set --name AWS_SECRET_ACCESS_KEY
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - gh and aws CLIs installed
 */

import { execSync } from 'node:child_process';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

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
    credentials: ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
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
    credentials: ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
  },
);

// -- Agent with CLI allowed commands ------------------------------------------

export const githubAwsAgent = new Agent({
  name: 'devops_agent',
  model: llmModel,
  tools: [ghListPrs, ghCreatePr, awsListS3Buckets, awsGetCallerIdentity],
  cliConfig: { enabled: true, allowedCommands: ['gh', 'aws'] },
  instructions:
    'You are a DevOps assistant. You can manage GitHub pull requests and ' +
    'inspect AWS resources. Always confirm destructive actions before proceeding.',
});

// -- Run ----------------------------------------------------------------------

const task = process.argv.slice(2).join(' ') || 'Who am I in AWS, and list my S3 buckets?';

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(githubAwsAgent);
    await runtime.serve(githubAwsAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(githubAwsAgent, task);
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('16c-credentials-cli-tools.ts') || process.argv[1]?.endsWith('16c-credentials-cli-tools.js')) {
  main().catch(console.error);
}
