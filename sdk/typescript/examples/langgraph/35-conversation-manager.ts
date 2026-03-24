/**
 * Conversation Manager -- advanced conversation history with summarization.
 *
 * Demonstrates:
 *   - Maintaining a sliding window of recent messages
 *   - Auto-summarizing older messages to stay within context limits
 *   - Separate system prompt and conversation turns in state
 *   - Practical use case: long-running chatbot that handles context limits
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------
interface Message {
  role: string;
  content: string;
}

interface ConversationState {
  newMessage: string;
  history: Message[];
  summary: string;
  response: string;
}

const WINDOW_SIZE = 6;
const SUMMARY_THRESHOLD = 8;

// ---------------------------------------------------------------------------
// Session store (simulates cross-turn persistence)
// ---------------------------------------------------------------------------
const sessions: Record<string, { history: Message[]; summary: string }> = {};

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function maybeSummarize(state: ConversationState): Partial<ConversationState> {
  if (state.history.length <= SUMMARY_THRESHOLD) return {};

  const oldMessages = state.history.slice(0, -WINDOW_SIZE);
  const recentMessages = state.history.slice(-WINDOW_SIZE);

  const conversationText = oldMessages
    .map((m) => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
    .join('\n');

  // Mock summarization
  const newSummary = `[Summary of ${oldMessages.length} messages: Discussion covered ${conversationText.slice(0, 100)}...]`;

  const combined = state.summary
    ? `${state.summary}\n\n${newSummary}`
    : newSummary;

  return { history: recentMessages, summary: combined };
}

function respond(state: ConversationState): Partial<ConversationState> {
  const msg = state.newMessage.toLowerCase();
  let response: string;

  if (msg.includes('where') && msg.includes('start')) {
    response =
      'Great question! I recommend starting with the official Python tutorial at python.org. ' +
      'It covers the basics from variables and control flow to functions and modules.';
  } else if (msg.includes('list') && msg.includes('tuple')) {
    response =
      'Lists are mutable (you can change them after creation) while tuples are immutable. ' +
      'Lists use square brackets [], tuples use parentheses ().';
  } else if (msg.includes('dictionary') || msg.includes('dict')) {
    response =
      'Here is a quick example: person = {"name": "Alice", "age": 30}. ' +
      'Access values with person["name"]. Dictionaries store key-value pairs.';
  } else if (msg.includes('exception') || msg.includes('error')) {
    response =
      'Use try/except blocks: try: ... except ValueError as e: print(e). ' +
      'You can catch specific exceptions and handle them gracefully.';
  } else if (msg.includes('decorator')) {
    response =
      'A decorator is a function that wraps another function to extend its behavior. ' +
      'Use @decorator_name syntax above a function definition.';
  } else {
    response = `That's a good question about Python. Let me help you with that topic.`;
  }

  const newHistory = [
    ...state.history,
    { role: 'user', content: state.newMessage },
    { role: 'assistant', content: response },
  ];

  return { history: newHistory, response };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'conversation_manager',

  invoke: async (input: Record<string, unknown>, config?: Record<string, unknown>) => {
    const newMessage = (input.input as string) ?? '';
    const sessionId = (config?.configurable as Record<string, unknown>)?.thread_id as string ?? 'default';

    // Load session
    const session = sessions[sessionId] ?? { history: [], summary: '' };

    let state: ConversationState = {
      newMessage,
      history: session.history,
      summary: session.summary,
      response: '',
    };

    state = { ...state, ...maybeSummarize(state) };
    state = { ...state, ...respond(state) };

    // Save session
    sessions[sessionId] = { history: state.history, summary: state.summary };

    return { output: state.response };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['summarize', {}],
      ['respond', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'summarize'],
      ['summarize', 'respond'],
      ['respond', '__end__'],
    ],
  }),

  nodes: new Map([
    ['summarize', {}],
    ['respond', {}],
  ]),

  stream: async function* (input: Record<string, unknown>, config?: Record<string, unknown>) {
    const newMessage = (input.input as string) ?? '';
    const sessionId = (config?.configurable as Record<string, unknown>)?.thread_id as string ?? 'default';
    const session = sessions[sessionId] ?? { history: [], summary: '' };

    let state: ConversationState = {
      newMessage,
      history: session.history,
      summary: session.summary,
      response: '',
    };

    state = { ...state, ...maybeSummarize(state) };
    yield ['updates', { summarize: { summary: state.summary } }];

    state = { ...state, ...respond(state) };
    yield ['updates', { respond: { response: state.response } }];

    sessions[sessionId] = { history: state.history, summary: state.summary };
    yield ['values', { output: state.response }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const turns = [
    'Hi! I\'m learning Python. Where should I start?',
    'What\'s the difference between a list and a tuple?',
    'Can you give me a quick example of a dictionary?',
    'How does exception handling work?',
    'What is a decorator in Python?',
  ];

  const runtime = new AgentRuntime();
  try {
    for (const turn of turns) {
      const result = await runtime.run(graph, turn, { sessionId: 'user-session-001' });
      console.log(`You: ${turn}`);
      result.printResult();
      console.log();
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
