/**
 * 70 - Customer Engineering Support Agent.
 *
 * Takes a Zendesk ticket number and investigates across Zendesk, JIRA,
 * HubSpot, Notion (runbooks), and GitHub to produce a solution with a
 * priority rating.
 *
 * Required credentials (set via `agentspan credentials set`):
 *   ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN
 *   JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
 *   HUBSPOT_ACCESS_TOKEN
 *   NOTION_API_KEY, NOTION_RUNBOOK_DB_ID
 *   GITHUB_TOKEN, GITHUB_ORG
 *
 * Requirements:
 *   - Conductor server
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, RegexGuardrail, agentTool, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Credential lists --------------------------------------------------------

const ZENDESK_CREDS = ['ZENDESK_SUBDOMAIN', 'ZENDESK_EMAIL', 'ZENDESK_API_TOKEN'];
const JIRA_CREDS = ['JIRA_BASE_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN'];
const HUBSPOT_CREDS = ['HUBSPOT_ACCESS_TOKEN'];
const NOTION_CREDS = ['NOTION_API_KEY', 'NOTION_RUNBOOK_DB_ID'];
const GITHUB_CREDS = ['GITHUB_TOKEN', 'GITHUB_ORG'];
const ALL_CREDS = [...ZENDESK_CREDS, ...JIRA_CREDS, ...HUBSPOT_CREDS, ...NOTION_CREDS, ...GITHUB_CREDS];

// -- Zendesk tools -----------------------------------------------------------

const getZendeskTicket = tool(
  async (args: { ticketId: string }) => {
    // In production, this would call the Zendesk API
    return { id: args.ticketId, subject: 'API timeout errors', status: 'open', priority: 'high' };
  },
  {
    name: 'get_zendesk_ticket',
    description: 'Fetch a Zendesk support ticket by its ID.',
    inputSchema: z.object({ ticketId: z.string() }),
    credentials: ZENDESK_CREDS,
  },
);

const searchZendeskTickets = tool(
  async (args: { query: string }) => {
    return { count: 0, tickets: [] };
  },
  {
    name: 'search_zendesk_tickets',
    description: 'Search Zendesk for tickets matching a query.',
    inputSchema: z.object({ query: z.string() }),
    credentials: ZENDESK_CREDS,
  },
);

// -- JIRA tools --------------------------------------------------------------

const searchJiraIssues = tool(
  async (args: { jql: string }) => {
    return { total: 0, issues: [] };
  },
  {
    name: 'search_jira_issues',
    description: 'Search JIRA issues using JQL.',
    inputSchema: z.object({ jql: z.string() }),
    credentials: JIRA_CREDS,
  },
);

const getJiraIssue = tool(
  async (args: { issueKey: string }) => {
    return { key: args.issueKey, summary: 'Not found', status: 'unknown' };
  },
  {
    name: 'get_jira_issue',
    description: 'Get full details of a specific JIRA issue.',
    inputSchema: z.object({ issueKey: z.string() }),
    credentials: JIRA_CREDS,
  },
);

// -- HubSpot tools -----------------------------------------------------------

const searchHubspotCompany = tool(
  async (args: { companyName: string }) => {
    return { count: 0, companies: [] };
  },
  {
    name: 'search_hubspot_company',
    description: 'Search HubSpot for a company by name.',
    inputSchema: z.object({ companyName: z.string() }),
    credentials: HUBSPOT_CREDS,
  },
);

const getHubspotContact = tool(
  async (args: { email: string }) => {
    return { id: null, name: '', email: args.email };
  },
  {
    name: 'get_hubspot_contact',
    description: 'Look up a HubSpot contact by email address.',
    inputSchema: z.object({ email: z.string() }),
    credentials: HUBSPOT_CREDS,
  },
);

// -- Notion tools ------------------------------------------------------------

const searchNotionRunbooks = tool(
  async (args: { query: string }) => {
    return { count: 0, runbooks: [] };
  },
  {
    name: 'search_notion_runbooks',
    description: 'Search Notion runbooks database for articles matching a query.',
    inputSchema: z.object({ query: z.string() }),
    credentials: NOTION_CREDS,
  },
);

const getNotionPageContent = tool(
  async (args: { pageId: string }) => {
    return { page_id: args.pageId, content: '' };
  },
  {
    name: 'get_notion_page_content',
    description: 'Retrieve the full content of a Notion page/runbook by its ID.',
    inputSchema: z.object({ pageId: z.string() }),
    credentials: NOTION_CREDS,
  },
);

// -- GitHub tools ------------------------------------------------------------

const searchGithubIssues = tool(
  async (args: { query: string; repo?: string }) => {
    return { total_count: 0, items: [] };
  },
  {
    name: 'search_github_issues',
    description: 'Search GitHub issues and pull requests.',
    inputSchema: z.object({
      query: z.string(),
      repo: z.string().optional(),
    }),
    credentials: GITHUB_CREDS,
  },
);

const searchGithubCode = tool(
  async (args: { query: string; repo?: string }) => {
    return { total_count: 0, files: [] };
  },
  {
    name: 'search_github_code',
    description: "Search GitHub code across the organization's repositories.",
    inputSchema: z.object({
      query: z.string(),
      repo: z.string().optional(),
    }),
    credentials: GITHUB_CREDS,
  },
);

const getGithubReleases = tool(
  async (args: { repo: string; limit?: number }) => {
    return { repo: args.repo, releases: [] };
  },
  {
    name: 'get_github_releases',
    description: 'Get recent releases for a GitHub repository.',
    inputSchema: z.object({
      repo: z.string(),
      limit: z.number().optional(),
    }),
    credentials: GITHUB_CREDS,
  },
);

const getGithubPullRequest = tool(
  async (args: { repo: string; prNumber: number }) => {
    return { number: args.prNumber, title: 'Not found', state: 'unknown' };
  },
  {
    name: 'get_github_pull_request',
    description: 'Get details of a specific GitHub pull request.',
    inputSchema: z.object({
      repo: z.string(),
      prNumber: z.number(),
    }),
    credentials: GITHUB_CREDS,
  },
);

// -- PII guardrail -----------------------------------------------------------

const piiGuardrail = new RegexGuardrail({
  name: 'ce_support_pii_guardrail',
  patterns: [
    '\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b', // credit card
    '\\b\\d{3}-\\d{2}-\\d{4}\\b',                              // SSN
  ],
  mode: 'block',
  position: 'output',
  onFail: 'retry',
  message: 'Do not include credit card numbers or SSNs in the output. Redact any PII.',
});

// -- Agent definitions -------------------------------------------------------

export const zendeskAgent = new Agent({
  name: 'zendesk_investigator',
  model: llmModel,
  instructions:
    'You are a Zendesk specialist. Fetch the given ticket and extract the core issue. ' +
    'Search for similar/related tickets to identify patterns.',
  tools: [getZendeskTicket, searchZendeskTickets],
  credentials: ZENDESK_CREDS,
});

export const jiraAgent = new Agent({
  name: 'jira_investigator',
  model: llmModel,
  instructions:
    'You are a JIRA specialist. Search for related engineering tickets. ' +
    'Check if there\'s an existing fix in progress.',
  tools: [searchJiraIssues, getJiraIssue],
  credentials: JIRA_CREDS,
});

export const hubspotAgent = new Agent({
  name: 'hubspot_investigator',
  model: llmModel,
  instructions:
    'You are a HubSpot CRM specialist. Look up the company and contact. ' +
    'Return plan tier, ARR, lifecycle stage, and account owner.',
  tools: [searchHubspotCompany, getHubspotContact],
  credentials: HUBSPOT_CREDS,
});

export const runbookAgent = new Agent({
  name: 'runbook_searcher',
  model: llmModel,
  instructions:
    'You are a Notion runbook specialist. Search for runbooks matching the symptoms. ' +
    'Read the most relevant ones for resolution instructions.',
  tools: [searchNotionRunbooks, getNotionPageContent],
  credentials: NOTION_CREDS,
});

export const githubAgent = new Agent({
  name: 'github_investigator',
  model: llmModel,
  instructions:
    'You are a GitHub code specialist. Search for related issues, PRs, and code. ' +
    'Check recent releases for fixes or regressions.',
  tools: [searchGithubIssues, searchGithubCode, getGithubReleases, getGithubPullRequest],
  credentials: GITHUB_CREDS,
});

const ORCHESTRATOR_INSTRUCTIONS =
  'You are a Customer Engineering Support Agent. Investigate a Zendesk ' +
  'support ticket and deliver a comprehensive analysis with a prioritized solution.\n\n' +
  'WORKFLOW:\n' +
  '1. Use the zendesk_investigator to fetch the ticket and find related tickets\n' +
  '2. In PARALLEL, use the other investigators to gather context\n' +
  '3. Synthesize all findings into a solution\n\n' +
  'PRIORITY GUIDE:\n' +
  '- P0: Production down for enterprise customer, data loss, security breach\n' +
  '- P1: Major feature broken for high-tier customer, significant revenue impact\n' +
  '- P2: Important feature degraded, workaround exists but painful\n' +
  '- P3: Non-critical feature issue, minor inconvenience\n' +
  '- P4: Enhancement request, cosmetic issue, documentation question';

export const ceSupportAgent = new Agent({
  name: 'ce_support_agent',
  model: llmModel,
  instructions: ORCHESTRATOR_INSTRUCTIONS,
  tools: [
    agentTool(zendeskAgent, { description: 'Investigate the Zendesk ticket' }),
    agentTool(hubspotAgent, { description: 'Look up customer context in HubSpot' }),
    agentTool(jiraAgent, { description: 'Search JIRA for related engineering issues' }),
    agentTool(runbookAgent, { description: 'Search Notion runbooks for resolution procedures' }),
    agentTool(githubAgent, { description: 'Search GitHub for related issues, PRs, code, and releases' }),
  ],
  credentials: ALL_CREDS,
  guardrails: [piiGuardrail.toGuardrailDef()],
  maxTurns: 15,
  temperature: 0.2,
});

// -- Run ---------------------------------------------------------------------

const ticketId = process.argv[2] ?? '12345';
const prompt = `Investigate Zendesk ticket #${ticketId} and provide a full analysis with solution and priority.`;

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(ceSupportAgent);
    // await runtime.serve(ceSupportAgent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    console.log(`\n--- Investigating ticket #${ticketId} ---\n`);
    const result = await runtime.run(ceSupportAgent, prompt);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('70-ce-support-agent.ts') || process.argv[1]?.endsWith('70-ce-support-agent.js')) {
  main().catch(console.error);
}
