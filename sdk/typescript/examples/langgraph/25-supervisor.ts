/**
 * Supervisor -- multi-agent supervisor pattern.
 *
 * Demonstrates:
 *   - A supervisor that decides which specialist agent to call next
 *   - Routing control flow based on the supervisor's decision
 *   - Collecting outputs from specialized sub-agents
 *   - Practical use case: research -> writing -> editing pipeline with supervisor
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("supervisor", route, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface SupervisorState {
  task: string;
  research: string;
  draft: string;
  finalArticle: string;
  nextAgent: string;
  completed: string[];
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function supervisor(state: SupervisorState): Partial<SupervisorState> {
  const completed = state.completed ?? [];
  if (!completed.includes('researcher')) return { nextAgent: 'researcher' };
  if (!completed.includes('writer')) return { nextAgent: 'writer' };
  if (!completed.includes('editor')) return { nextAgent: 'editor' };
  return { nextAgent: 'FINISH' };
}

function researcher(state: SupervisorState): Partial<SupervisorState> {
  const research =
    `Key findings on "${state.task}":\n` +
    `- LLMs are transforming code generation, review, and documentation\n` +
    `- Developer productivity gains of 30-55% reported in recent studies\n` +
    `- Concerns around code quality, security, and over-reliance persist\n` +
    `- New roles emerging: prompt engineers, AI-assisted architects`;
  const completed = [...(state.completed ?? []), 'researcher'];
  return { research, completed };
}

function writer(state: SupervisorState): Partial<SupervisorState> {
  const draft =
    `The Impact of Large Language Models on Software Development\n\n` +
    `Large language models are reshaping how software is built. ${state.research}\n\n` +
    `Companies across the industry are integrating AI coding assistants into their ` +
    `development workflows, with early results showing significant productivity gains.\n\n` +
    `However, the transition is not without challenges. Questions about code quality ` +
    `and security remain at the forefront of the discussion.`;
  const completed = [...(state.completed ?? []), 'writer'];
  return { draft, completed };
}

function editor(state: SupervisorState): Partial<SupervisorState> {
  const finalArticle =
    state.draft.replace(
      'are reshaping',
      'have fundamentally transformed',
    ) +
    `\n\nEditor's note: Article polished for clarity and flow.`;
  const completed = [...(state.completed ?? []), 'editor'];
  return { finalArticle, completed };
}

function route(state: SupervisorState): string {
  return state.nextAgent ?? 'FINISH';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'supervisor_multiagent',

  invoke: async (input: Record<string, unknown>) => {
    const task = (input.input as string) ?? '';
    let state: SupervisorState = {
      task,
      research: '',
      draft: '',
      finalArticle: '',
      nextAgent: '',
      completed: [],
    };

    // Supervisor loop
    for (let i = 0; i < 10; i++) {
      state = { ...state, ...supervisor(state) };
      const next = route(state);
      if (next === 'FINISH') break;

      if (next === 'researcher') state = { ...state, ...researcher(state) };
      else if (next === 'writer') state = { ...state, ...writer(state) };
      else if (next === 'editor') state = { ...state, ...editor(state) };
    }

    return { output: state.finalArticle };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['supervisor', {}],
      ['researcher', {}],
      ['writer', {}],
      ['editor', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'supervisor'],
      // Conditional: supervisor -> researcher | writer | editor | END
      ['researcher', 'supervisor'],
      ['writer', 'supervisor'],
      ['editor', 'supervisor'],
    ],
  }),

  nodes: new Map([
    ['supervisor', {}],
    ['researcher', {}],
    ['writer', {}],
    ['editor', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const task = (input.input as string) ?? '';
    let state: SupervisorState = {
      task,
      research: '',
      draft: '',
      finalArticle: '',
      nextAgent: '',
      completed: [],
    };

    for (let i = 0; i < 10; i++) {
      state = { ...state, ...supervisor(state) };
      yield ['updates', { supervisor: { nextAgent: state.nextAgent } }];

      const next = route(state);
      if (next === 'FINISH') break;

      if (next === 'researcher') {
        state = { ...state, ...researcher(state) };
        yield ['updates', { researcher: { research: state.research } }];
      } else if (next === 'writer') {
        state = { ...state, ...writer(state) };
        yield ['updates', { writer: { draft: state.draft } }];
      } else if (next === 'editor') {
        state = { ...state, ...editor(state) };
        yield ['updates', { editor: { finalArticle: state.finalArticle } }];
      }
    }

    yield ['values', { output: state.finalArticle }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      graph,
      'The impact of large language models on software development',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
