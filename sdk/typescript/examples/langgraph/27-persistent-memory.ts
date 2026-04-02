/**
 * Persistent Memory -- cross-session state via checkpointing.
 *
 * Demonstrates:
 *   - MemorySaver for in-process cross-turn state
 *   - Configuring sessionId to maintain separate conversation histories per user
 *   - The graph accumulates conversation turns across multiple runtime.run() calls
 *   - Practical use case: multi-turn chatbot that remembers earlier exchanges
 */

import { StateGraph, START, END, Annotation, MemorySaver } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
interface MessageRecord {
  role: string;
  content: string;
}

const MemoryState = Annotation.Root({
  messages: Annotation<MessageRecord[]>({
    reducer: (_prev: MessageRecord[], next: MessageRecord[]) => next ?? _prev,
    default: () => [],
  }),
  user_name: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof MemoryState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function chat(state: State): Promise<Partial<State>> {
  const messages = state.messages || [];
  const lcMessages: Array<SystemMessage | HumanMessage | AIMessage> = [
    new SystemMessage(
      'You are a helpful assistant. Remember context from earlier in this conversation.',
    ),
  ];
  for (const m of messages) {
    if (m.role === 'user') lcMessages.push(new HumanMessage(m.content));
    else if (m.role === 'assistant') lcMessages.push(new AIMessage(m.content));
  }
  const response = await llm.invoke(lcMessages);
  const newMessages = [
    ...messages,
    { role: 'assistant', content: String(response.content) },
  ];
  return { messages: newMessages };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(MemoryState);
builder.addNode('chat', chat);
builder.addEdge(START, 'chat');
builder.addEdge('chat', END);

const checkpointer = new MemorySaver();
const graph = builder.compile({ checkpointer });

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Run on agentspan
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
    console.log(`Bob: ${msg}`);
    result.printResult();
    console.log();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents persistent_memory
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
    }
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('27-persistent-memory.ts') || process.argv[1]?.endsWith('27-persistent-memory.js')) {
  main().catch(console.error);
}
