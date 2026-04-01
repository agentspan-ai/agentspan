/**
 * Conversation Manager -- advanced conversation history with summarization.
 *
 * Demonstrates:
 *   - Maintaining a sliding window of recent messages
 *   - Auto-summarizing older messages to stay within context limits
 *   - Separate system prompt and conversation turns in state
 *   - Practical use case: long-running chatbot that handles context limits gracefully
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

const WINDOW_SIZE = 6;
const SUMMARY_THRESHOLD = 8;

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
interface Message {
  role: string;
  content: string;
}

const ConversationState = Annotation.Root({
  new_message: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  history: Annotation<Message[]>({
    reducer: (_prev: Message[], next: Message[]) => next ?? _prev,
    default: () => [],
  }),
  summary: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  response: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof ConversationState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function maybeSummarize(state: State): Promise<Partial<State>> {
  const history = state.history || [];
  if (history.length <= SUMMARY_THRESHOLD) {
    return {};
  }

  const oldMessages = history.slice(0, -WINDOW_SIZE);
  const recentMessages = history.slice(-WINDOW_SIZE);

  const conversationText = oldMessages
    .map((m) => `${m.role.charAt(0).toUpperCase() + m.role.slice(1)}: ${m.content}`)
    .join('\n');

  const response = await llm.invoke([
    new SystemMessage('Summarize the following conversation in 2-3 sentences, preserving key facts.'),
    new HumanMessage(conversationText),
  ]);

  let newSummary = typeof response.content === 'string' ? response.content.trim() : '';
  if (state.summary) {
    newSummary = `${state.summary}\n\n${newSummary}`;
  }

  return { history: recentMessages, summary: newSummary };
}

async function respond(state: State): Promise<Partial<State>> {
  let systemContent = 'You are a helpful, friendly assistant.';
  if (state.summary) {
    systemContent += `\n\nConversation summary so far:\n${state.summary}`;
  }

  const messages: (SystemMessage | HumanMessage | AIMessage)[] = [new SystemMessage(systemContent)];

  for (const m of state.history || []) {
    if (m.role === 'user') {
      messages.push(new HumanMessage(m.content));
    } else {
      messages.push(new AIMessage(m.content));
    }
  }

  messages.push(new HumanMessage(state.new_message));

  const aiResponse = await llm.invoke(messages);
  const responseContent = typeof aiResponse.content === 'string' ? aiResponse.content : '';
  const newHistory = [
    ...(state.history || []),
    { role: 'user', content: state.new_message },
    { role: 'assistant', content: responseContent },
  ];

  return { history: newHistory, response: responseContent };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(ConversationState);
builder.addNode('summarize', maybeSummarize);
builder.addNode('respond', respond);
builder.addEdge(START, 'summarize');
builder.addEdge('summarize', 'respond');
builder.addEdge('respond', END);

const graph = builder.compile();

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const turns = [
    "Hi! I'm learning Python. Where should I start?",
    "What's the difference between a list and a tuple?",
    'Can you give me a quick example of a dictionary?',
    'How does exception handling work?',
    'What is a decorator in Python?',
  ];

  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    for (const turn of turns) {
    const result = await runtime.run(graph, turn);
    console.log(`You: ${turn}`);
    console.log('Status:', result.status);
    result.printResult();
    console.log();
    }
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('35-conversation-manager.ts') || process.argv[1]?.endsWith('35-conversation-manager.js')) {
  main().catch(console.error);
}
