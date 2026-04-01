/**
 * Software Bug Assistant -- AgentTool + tools for bug triage.
 *
 * Mirrors the pattern from google/adk-samples/software-bug-assistant.
 * Demonstrates:
 *   - AgentTool wrapping a search sub-agent
 *   - Local ticket CRUD (in-memory store)
 *   - Multi-tool orchestration for bug triage
 *
 * Architecture:
 *   software_assistant (root agent)
 *     tools:
 *       - get_current_date
 *       - AgentTool(search_agent)  -- sub-agent for research
 *       - search_tickets           -- local DB
 *       - create_ticket            -- local DB
 *       - update_ticket            -- local DB
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool, AgentTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── In-memory ticket store ───────────────────────────────────────────

interface Ticket {
  id: string;
  title: string;
  status: string;
  priority: string;
  github_issue?: number;
  description: string;
  created: string;
}

const tickets: Record<string, Ticket> = {
  'COND-001': {
    id: 'COND-001',
    title: 'TaskStatusListener not invoked for system task lifecycle transitions',
    status: 'open',
    priority: 'high',
    github_issue: 847,
    description:
      'TaskStatusListener notifications are only fully wired for ' +
      'worker tasks (SIMPLE/custom). Both synchronous and asynchronous ' +
      'system tasks miss lifecycle transition callbacks.',
    created: '2026-03-10',
  },
  'COND-002': {
    id: 'COND-002',
    title: 'Support reasonForIncompletion in fail_task event handlers',
    status: 'open',
    priority: 'medium',
    github_issue: 858,
    description:
      'When an event handler uses action: fail_task, there is no way ' +
      'to set reasonForIncompletion. Need to support this field so ' +
      'failed tasks have meaningful error messages.',
    created: '2026-03-13',
  },
  'COND-003': {
    id: 'COND-003',
    title: 'Optimize /workflowDefs page: paginate latest-versions API',
    status: 'open',
    priority: 'medium',
    github_issue: 781,
    description:
      'The UI /workflowDefs page calls GET /metadata/workflow which ' +
      'returns all versions of all workflows. This causes slow page ' +
      'loads. Need pagination for the latest-versions endpoint.',
    created: '2026-02-18',
  },
};

let nextId = 4;

// ── Function tools ───────────────────────────────────────────────────

const getCurrentDate = new FunctionTool({
  name: 'get_current_date',
  description: "Get today's date.",
  parameters: z.object({}),
  execute: async () => {
    return { date: new Date().toISOString().split('T')[0] };
  },
});

const searchTickets = new FunctionTool({
  name: 'search_tickets',
  description: 'Search the internal bug ticket database for Conductor issues.',
  parameters: z.object({
    query: z
      .string()
      .describe('Search term to match against ticket titles and descriptions'),
  }),
  execute: async (args: { query: string }) => {
    const queryLower = args.query.toLowerCase();
    const matches = Object.values(tickets).filter(
      (t) =>
        t.title.toLowerCase().includes(queryLower) ||
        t.description.toLowerCase().includes(queryLower),
    );
    return { query: args.query, count: matches.length, tickets: matches };
  },
});

const createTicket = new FunctionTool({
  name: 'create_ticket',
  description: 'Create a new bug ticket in the internal tracker.',
  parameters: z.object({
    title: z.string().describe('Short title for the bug'),
    description: z.string().describe('Detailed description of the issue'),
    priority: z
      .string()
      .describe('Priority level (low, medium, high, critical)')
      .default('medium'),
  }),
  execute: async (args: {
    title: string;
    description: string;
    priority?: string;
  }) => {
    const ticketId = `COND-${String(nextId).padStart(3, '0')}`;
    nextId += 1;
    const ticket: Ticket = {
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
});

const updateTicket = new FunctionTool({
  name: 'update_ticket',
  description: "Update an existing bug ticket's status or priority.",
  parameters: z.object({
    ticket_id: z.string().describe('The ticket ID (e.g. COND-001)'),
    status: z
      .string()
      .describe(
        'New status (open, in_progress, resolved, closed). Leave empty to skip.',
      )
      .default(''),
    priority: z
      .string()
      .describe('New priority (low, medium, high, critical). Leave empty to skip.')
      .default(''),
  }),
  execute: async (args: {
    ticket_id: string;
    status?: string;
    priority?: string;
  }) => {
    const ticket = tickets[args.ticket_id.toUpperCase()];
    if (!ticket) {
      return { error: `Ticket ${args.ticket_id} not found` };
    }
    if (args.status) {
      ticket.status = args.status;
    }
    if (args.priority) {
      ticket.priority = args.priority;
    }
    return { updated: true, ticket };
  },
});

// ── Search sub-agent (wrapped as AgentTool) ──────────────────────────

const searchWeb = new FunctionTool({
  name: 'search_web',
  description:
    'Search the web for information about a Conductor bug or workflow issue.',
  parameters: z.object({
    query: z.string().describe('The search query'),
  }),
  execute: async (args: { query: string }) => {
    const results: Record<string, { source: string; answer: string }> = {
      'task status listener': {
        source: 'Conductor Docs',
        answer:
          'TaskStatusListener is only wired for SIMPLE tasks. System ' +
          'tasks like HTTP, INLINE, SUB_WORKFLOW bypass the listener ' +
          'because they complete synchronously within the decider loop.',
      },
      'do_while loop': {
        source: 'GitHub PR #820',
        answer:
          "DO_WHILE tasks with 'items' now pass validation without " +
          'loopCondition. Fixed in PR #820 -- the validator was ' +
          'unconditionally requiring loopCondition for all DO_WHILE tasks.',
      },
      'event handler fail': {
        source: 'GitHub Issue #858',
        answer:
          'Event handlers with action: fail_task cannot set ' +
          "reasonForIncompletion. A proposed fix adds an optional " +
          "'reason' field to the fail_task action configuration.",
      },
      'workflow def pagination': {
        source: 'GitHub Issue #781',
        answer:
          'The /metadata/workflow endpoint returns all versions of all ' +
          'workflows causing slow UI loads. A pagination API for ' +
          'latest-versions is proposed to fix this.',
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
});

export const searchAgent = new LlmAgent({
  name: 'search_agent',
  model,
  description: 'A technical search assistant for Conductor workflow issues.',
  instruction:
    'You are a technical search assistant specializing in Conductor ' +
    '(conductor-oss/conductor) workflow orchestration. Use the search_web ' +
    'tool to find relevant information about bugs, errors, and Conductor ' +
    'configuration issues. Provide concise, actionable answers.',
  tools: [searchWeb],
});

// ── Root agent ───────────────────────────────────────────────────────

export const softwareAssistant = new LlmAgent({
  name: 'software_assistant',
  model,
  instruction:
    'You are a software bug triage assistant for the Conductor workflow ' +
    'orchestration engine (https://github.com/conductor-oss/conductor).\n\n' +
    'Your capabilities:\n' +
    '1. Search and manage internal bug tickets (search_tickets, create_ticket, ' +
    'update_ticket)\n' +
    '2. Research Conductor issues using the search_agent tool\n' +
    '3. Cross-reference findings with internal tickets\n\n' +
    'When triaging:\n' +
    '- Search internal tickets first\n' +
    '- Research any unfamiliar issues with the search_agent\n' +
    '- Create internal tickets for new issues not yet tracked\n' +
    '- Suggest next steps, referencing GitHub issue/PR numbers',
  tools: [
    getCurrentDate,
    new AgentTool({ agent: searchAgent }),
    searchTickets,
    createTicket,
    updateTicket,
  ],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(softwareAssistant);
    // await runtime.serve(softwareAssistant);
    // Direct run for local development:
    const result = await runtime.run(
    softwareAssistant,
    'Review our internal tickets and research any related Conductor issues. ' +
    'Pay attention to the DO_WHILE fix (PR #820) and the TaskStatusListener ' +
    'issue. Give me a triage summary.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('33-software-bug-assistant.ts') || process.argv[1]?.endsWith('33-software-bug-assistant.js')) {
  main().catch(console.error);
}
