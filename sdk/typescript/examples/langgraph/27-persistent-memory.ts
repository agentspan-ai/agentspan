/**
 * Persistent Memory -- cross-session state via checkpointing.
 *
 * Demonstrates:
 *   - MemorySaver for in-process cross-turn state
 *   - Configuring thread_id to maintain separate conversation histories per user
 *   - The graph accumulates conversation turns across multiple runtime.run() calls
 *   - Practical use case: multi-turn chatbot that remembers earlier exchanges
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   import { MemorySaver } from '@langchain/langgraph/checkpoint/memory';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface Message {
  role: string;
  content: string;
}

interface MemoryState {
  messages: Message[];
  userName: string;
}

// ---------------------------------------------------------------------------
// In-memory store (simulates MemorySaver)
// ---------------------------------------------------------------------------
const sessionStore: Record<string, Message[]> = {};

// ---------------------------------------------------------------------------
// Node function
// ---------------------------------------------------------------------------
function chat(state: MemoryState, sessionId: string): Partial<MemoryState> {
  const existing = sessionStore[sessionId] ?? [];
  const allMessages = [...existing, ...state.messages];

  // Mock LLM response based on context
  const lastMsg = allMessages[allMessages.length - 1]?.content ?? '';
  let response: string;

  if (lastMsg.toLowerCase().includes('my name is')) {
    const name = lastMsg.match(/my name is (\w+)/i)?.[1] ?? 'friend';
    response = `Nice to meet you, ${name}! How can I help you today?`;
  } else if (lastMsg.toLowerCase().includes("what's my name") || lastMsg.toLowerCase().includes('what is my name')) {
    const nameMsg = allMessages.find((m) => m.content.toLowerCase().includes('my name is'));
    const name = nameMsg?.content.match(/my name is (\w+)/i)?.[1];
    response = name
      ? `Your name is ${name}!`
      : `I don't think you've told me your name yet.`;
  } else if (lastMsg.toLowerCase().includes('what did i just tell')) {
    const prev = allMessages[allMessages.length - 3]?.content ?? 'something';
    response = `You previously told me: "${prev}"`;
  } else if (lastMsg.toLowerCase().includes('hobby') || lastMsg.toLowerCase().includes('hiking')) {
    const hobbyMsg = allMessages.find((m) => m.content.toLowerCase().includes('hiking') || m.content.toLowerCase().includes('hobby'));
    response = hobbyMsg
      ? `You mentioned you love hiking!`
      : `I don't recall you mentioning a hobby.`;
  } else {
    response = `I understand. Let me help you with that.`;
  }

  const newMessages = [
    ...allMessages,
    { role: 'assistant', content: response },
  ];
  sessionStore[sessionId] = newMessages;

  return { messages: newMessages };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'persistent_memory_chatbot',

  invoke: async (input: Record<string, unknown>, config?: Record<string, unknown>) => {
    const userMsg = (input.input as string) ?? '';
    const sessionId = (config?.configurable as Record<string, unknown>)?.thread_id as string ?? 'default';
    const state: MemoryState = {
      messages: [{ role: 'user', content: userMsg }],
      userName: '',
    };

    const updated = chat(state, sessionId);
    const lastMsg = updated.messages?.[updated.messages.length - 1]?.content ?? '';
    return { output: lastMsg };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['chat', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'chat'],
      ['chat', '__end__'],
    ],
  }),

  nodes: new Map([['chat', {}]]),

  stream: async function* (input: Record<string, unknown>, config?: Record<string, unknown>) {
    const userMsg = (input.input as string) ?? '';
    const sessionId = (config?.configurable as Record<string, unknown>)?.thread_id as string ?? 'default';
    const state: MemoryState = {
      messages: [{ role: 'user', content: userMsg }],
      userName: '',
    };

    const updated = chat(state, sessionId);
    const lastMsg = updated.messages?.[updated.messages.length - 1]?.content ?? '';
    yield ['updates', { chat: { messages: updated.messages } }];
    yield ['values', { output: lastMsg }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('=== Alice\'s conversation ===');
    for (const msg of ['Hi, my name is Alice!', "What's my name?", 'What did I just tell you?']) {
      const result = await runtime.run(graph, msg, { sessionId: 'alice' });
      console.log(`Alice: ${msg}`);
      result.printResult();
      console.log();
    }

    console.log("=== Bob's conversation (separate session) ===");
    for (const msg of ["I'm Bob. I love hiking.", 'What hobby did I mention?']) {
      const result = await runtime.run(graph, msg, { sessionId: 'bob' });
      console.log(`Bob:  ${msg}`);
      result.printResult();
      console.log();
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
