/**
 * Streaming Tokens -- streaming intermediate LLM output token by token.
 *
 * Demonstrates:
 *   - Using graph.stream() with streamMode "messages" to receive tokens incrementally
 *   - Printing partial output as it arrives for a real-time feel
 *   - How LangGraph exposes AIMessageChunk events during generation
 *   - Practical use case: streaming a long-form answer to the terminal
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage, AIMessageChunk } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM (streaming enabled)
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0, streaming: true });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const StreamState = Annotation.Root({
  messages: Annotation<Array<HumanMessage | SystemMessage | AIMessageChunk>>({
    reducer: (
      _prev: Array<HumanMessage | SystemMessage | AIMessageChunk>,
      next: Array<HumanMessage | SystemMessage | AIMessageChunk>,
    ) => next ?? _prev,
    default: () => [],
  }),
});

type State = typeof StreamState.State;

// ---------------------------------------------------------------------------
// Node function
// ---------------------------------------------------------------------------
async function generate(state: State): Promise<Partial<State>> {
  const messages = state.messages || [];
  const response = await llm.invoke(messages);
  return { messages: [...messages, response] };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(StreamState);
builder.addNode('generate', generate);
builder.addEdge(START, 'generate');
builder.addEdge('generate', END);
const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Stream to console
// ---------------------------------------------------------------------------
async function streamToConsole(prompt: string) {
  const inputState = {
    messages: [
      new SystemMessage('You are a helpful assistant. Answer thoroughly.'),
      new HumanMessage(prompt),
    ],
  };

  console.log('Streaming response:\n');
  const stream = await graph.stream(inputState, { streamMode: 'messages' });
  for await (const [_eventType, chunk] of stream) {
    if (chunk instanceof AIMessageChunk && chunk.content) {
      process.stdout.write(String(chunk.content));
    }
  }
  console.log('\n');
}

const PROMPT =
  'Explain the concept of gradient descent in machine learning in about 150 words.';

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents streaming_tokens
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);

    // Native LangGraph token-streaming alternative:
    // await streamToConsole(PROMPT);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('28-streaming-tokens.ts') || process.argv[1]?.endsWith('28-streaming-tokens.js')) {
  main().catch(console.error);
}
