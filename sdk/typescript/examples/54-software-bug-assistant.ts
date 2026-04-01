/**
 * 54 - Software Bug Assistant — agentTool + mcpTool for bug triage.
 *
 * Demonstrates:
 *   - agentTool wrapping a search sub-agent
 *   - mcpTool for live GitHub issue/PR lookup on conductor-oss/conductor
 *   - tool() for local ticket CRUD (in-memory store)
 *
 * Requirements:
 *   - Conductor server with AgentTool + MCP support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 *   - GH_TOKEN in environment (optional, for GitHub MCP)
 */

import { z } from 'zod';
import { Agent, AgentRuntime, agentTool, tool, mcpTool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- In-memory ticket store --------------------------------------------------

const tickets: Record<string, Record<string, unknown>> = {
  'COND-001': {
    id: 'COND-001',
    title: 'TaskStatusListener not invoked for system task lifecycle transitions',
    status: 'open',
    priority: 'high',
    github_issue: 847,
    description:
      'TaskStatusListener notifications are only fully wired for worker tasks (SIMPLE/custom). ' +
      'Both synchronous and asynchronous system tasks miss lifecycle transition callbacks.',
    created: '2026-03-10',
  },
  'COND-002': {
    id: 'COND-002',
    title: 'Support reasonForIncompletion in fail_task event handlers',
    status: 'open',
    priority: 'medium',
    github_issue: 858,
    description:
      'When an event handler uses action: fail_task, there is no way to set reasonForIncompletion. ' +
      'Need to support this field so failed tasks have meaningful error messages.',
    created: '2026-03-13',
  },
  'COND-003': {
    id: 'COND-003',
    title: 'Optimize /workflowDefs page: paginate latest-versions API',
    status: 'open',
    priority: 'medium',
    github_issue: 781,
    description:
      'The UI /workflowDefs page calls GET /metadata/workflow which returns all versions ' +
      'of all workflows. This causes slow page loads. Need pagination for the latest-versions endpoint.',
    created: '2026-02-18',
  },
};

let nextId = 4;

// -- Function tools ----------------------------------------------------------

const getCurrentDate = tool(
  async () => {
    return { date: new Date().toISOString().split('T')[0] };
  },
  {
    name: 'get_current_date',
    description: "Get today's date.",
    inputSchema: z.object({}),
  },
);

const searchTickets = tool(
  async (args: { query: string }) => {
    const queryLower = args.query.toLowerCase();
    const matches = Object.values(tickets).filter(
      (t) =>
        String(t.title).toLowerCase().includes(queryLower) ||
        String(t.description).toLowerCase().includes(queryLower),
    );
    return { query: args.query, count: matches.length, tickets: matches };
  },
  {
    name: 'search_tickets',
    description: 'Search the internal bug ticket database for Conductor issues.',
    inputSchema: z.object({
      query: z.string().describe('Search term to match against ticket titles and descriptions'),
    }),
  },
);

const createTicket = tool(
  async (args: { title: string; description: string; priority?: string }) => {
    const ticketId = `COND-${String(nextId).padStart(3, '0')}`;
    nextId++;
    const ticket = {
      id: ticketId,
      title: args.title,
      status: 'open',
      priority: args.priority ?? 'medium',
      description: args.description,
      created: new Date().toISOString().split('T')[0],
    };
    tickets[ticketId] = ticket;
    return { created: true, ticket };
  },
  {
    name: 'create_ticket',
    description: 'Create a new bug ticket in the internal tracker.',
    inputSchema: z.object({
      title: z.string().describe('Short title for the bug'),
      description: z.string().describe('Detailed description of the issue'),
      priority: z.string().optional().describe('Priority level (low, medium, high, critical)'),
    }),
  },
);

const updateTicket = tool(
  async (args: { ticketId: string; status?: string; priority?: string }) => {
    const ticket = tickets[args.ticketId.toUpperCase()];
    if (!ticket) {
      return { error: `Ticket ${args.ticketId} not found` };
    }
    if (args.status) ticket.status = args.status;
    if (args.priority) ticket.priority = args.priority;
    return { updated: true, ticket };
  },
  {
    name: 'update_ticket',
    description: "Update an existing bug ticket's status or priority.",
    inputSchema: z.object({
      ticketId: z.string().describe('The ticket ID (e.g. COND-001)'),
      status: z.string().optional().describe('New status (open, in_progress, resolved, closed)'),
      priority: z.string().optional().describe('New priority (low, medium, high, critical)'),
    }),
  },
);

// -- Search sub-agent (wrapped as agentTool) ---------------------------------

const searchWebTool = tool(
  async (args: { query: string }) => {
    const results: Record<string, { source: string; answer: string }> = {
      'task status listener': {
        source: 'Conductor Docs',
        answer:
          'TaskStatusListener is only wired for SIMPLE tasks. System tasks like HTTP, INLINE, ' +
          'SUB_WORKFLOW bypass the listener because they complete synchronously within the decider loop.',
      },
      do_while: {
        source: 'GitHub PR #820',
        answer:
          "DO_WHILE tasks with 'items' now pass validation without loopCondition. Fixed in PR #820.",
      },
      'event handler fail': {
        source: 'GitHub Issue #858',
        answer:
          'Event handlers with action: fail_task cannot set reasonForIncompletion. ' +
          "A proposed fix adds an optional 'reason' field to the fail_task action configuration.",
      },
      'workflow def pagination': {
        source: 'GitHub Issue #781',
        answer:
          'The /metadata/workflow endpoint returns all versions of all workflows causing slow UI loads. ' +
          'A pagination API for latest-versions is proposed to fix this.',
      },
    };
    const queryLower = args.query.toLowerCase();
    for (const [key, val] of Object.entries(results)) {
      if (queryLower.includes(key)) {
        return { query: args.query, found: true, ...val };
      }
    }
    return { query: args.query, found: false, summary: 'No specific results found.' };
  },
  {
    name: 'search_web',
    description: 'Search the web for information about a Conductor bug or workflow issue.',
    inputSchema: z.object({
      query: z.string().describe('The search query'),
    }),
  },
);

export const searchAgent = new Agent({
  name: 'search_agent_54',
  model: llmModel,
  instructions:
    'You are a technical search assistant specializing in Conductor ' +
    '(conductor-oss/conductor) workflow orchestration. Use the search_web ' +
    'tool to find relevant information about bugs, errors, and Conductor ' +
    'configuration issues. Provide concise, actionable answers.',
  tools: [searchWebTool],
});

// -- GitHub MCP tools --------------------------------------------------------

const githubMcpUrl = process.env.GITHUB_MCP_URL ?? 'https://api.githubcopilot.com/mcp/';
const githubToken = process.env.GH_TOKEN ?? '';

const github = mcpTool({
  serverUrl: githubMcpUrl,
  name: 'github_mcp',
  description:
    'GitHub tools for accessing the conductor-oss/conductor repository -- ' +
    'search issues, list open pull requests, and get issue details',
  headers: { Authorization: `Bearer ${githubToken}` },
  toolNames: [
    'search_repositories',
    'search_issues',
    'list_issues',
    'get_issue',
    'list_pull_requests',
    'get_pull_request',
  ],
});

// -- Root agent --------------------------------------------------------------

export const softwareAssistant = new Agent({
  name: 'software_assistant_54',
  model: llmModel,
  instructions:
    'You are a software bug triage assistant for the Conductor workflow ' +
    'orchestration engine (https://github.com/conductor-oss/conductor).\n\n' +
    'Your capabilities:\n' +
    '1. Search and manage internal bug tickets (search_tickets, create_ticket, update_ticket)\n' +
    '2. Research Conductor issues using the search_agent tool\n' +
    '3. Look up real GitHub issues and PRs on conductor-oss/conductor using the GitHub MCP tools\n' +
    '4. Cross-reference GitHub issues with internal tickets\n\n' +
    'When triaging:\n' +
    '- Use GitHub MCP tools to fetch the latest issues and PRs from conductor-oss/conductor\n' +
    '- Cross-reference with internal tickets (search_tickets)\n' +
    '- Research any unfamiliar issues with the search_agent\n' +
    '- Create internal tickets for new issues not yet tracked\n' +
    '- Suggest next steps, referencing GitHub issue/PR numbers',
  tools: [
    getCurrentDate,
    agentTool(searchAgent),
    github,
    searchTickets,
    createTicket,
    updateTicket,
  ],
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(softwareAssistant);
    // await runtime.serve(softwareAssistant);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    softwareAssistant,
    'Review the latest open issues and PRs on conductor-oss/conductor. ' +
    'Check if any of them relate to our internal tickets. ' +
    'Pay attention to the DO_WHILE fix (PR #820) and the scheduler ' +
    'persistence PRs. Give me a triage summary.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('54-software-bug-assistant.ts') || process.argv[1]?.endsWith('54-software-bug-assistant.js')) {
  main().catch(console.error);
}
