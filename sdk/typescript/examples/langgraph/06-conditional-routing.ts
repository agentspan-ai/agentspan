/**
 * Conditional Routing -- StateGraph with addConditionalEdges.
 *
 * Demonstrates:
 *   - Using addConditionalEdges to branch based on state content
 *   - A sentiment classifier that routes to positive, negative, or neutral handlers
 *   - Multiple terminal nodes converging to END
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const SentimentState = Annotation.Root({
  text: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  sentiment: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => 'neutral',
  }),
  response: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof SentimentState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function classify(state: State): Partial<State> {
  const text = state.text.toLowerCase();
  const positiveWords = ['thrilled', 'promoted', 'love', 'great', 'happy', 'amazing', 'excellent'];
  const negativeWords = ['sad', 'angry', 'terrible', 'hate', 'awful', 'disappointed', 'frustrated'];

  const posCount = positiveWords.filter((w) => text.includes(w)).length;
  const negCount = negativeWords.filter((w) => text.includes(w)).length;

  if (posCount > negCount) return { sentiment: 'positive' };
  if (negCount > posCount) return { sentiment: 'negative' };
  return { sentiment: 'neutral' };
}

function routeSentiment(state: State): string {
  return state.sentiment;
}

function handlePositive(_state: State): Partial<State> {
  return {
    response:
      "That's wonderful news! Congratulations on your promotion! " +
      'Your hard work and dedication are clearly paying off. Keep up the amazing work!',
  };
}

function handleNegative(_state: State): Partial<State> {
  return {
    response:
      "I'm sorry to hear that. It's completely valid to feel that way. " +
      'Remember, difficult times are temporary and things can improve. ' +
      'Is there anything specific I can help with?',
  };
}

function handleNeutral(_state: State): Partial<State> {
  return {
    response:
      "Thank you for sharing that. I'm here to help if you need anything. " +
      "Feel free to ask me any questions or share more about what's on your mind.",
  };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(SentimentState);
builder.addNode('classify', classify);
builder.addNode('positive', handlePositive);
builder.addNode('negative', handleNegative);
builder.addNode('neutral', handleNeutral);
builder.addEdge(START, 'classify');
builder.addConditionalEdges('classify', routeSentiment, {
  positive: 'positive',
  negative: 'negative',
  neutral: 'neutral',
});
builder.addEdge('positive', END);
builder.addEdge('negative', END);
builder.addEdge('neutral', END);

const graph = builder.compile();

// Add agentspan metadata for extraction (no LLM in this pipeline example)
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
    const result = await runtime.run(
      graph,
      "I just got promoted at work and I'm thrilled!",
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
