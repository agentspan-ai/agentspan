/**
 * Chat History -- maintaining conversation history across multiple turns.
 *
 * Demonstrates:
 *   - Accumulating HumanMessage/AIMessage pairs across turns
 *   - ChatOpenAI responding with full conversation context
 *   - Multi-turn conversation where the model recalls prior information
 *   - Running via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import type { BaseMessage } from '@langchain/core/messages';
import { RunnableLambda } from '@langchain/core/runnables';
import { AgentRuntime } from '../../src/index.js';

// ── Chat with history ────────────────────────────────────

class ChatWithHistory {
  private model: ChatOpenAI;
  private history: BaseMessage[];

  constructor() {
    this.model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0.3 });
    this.history = [
      new SystemMessage(
        'You are a friendly, helpful assistant. Remember everything the user tells you ' +
        'within this conversation and reference it when relevant. Keep responses concise.'
      ),
    ];
  }

  async chat(message: string): Promise<string> {
    this.history.push(new HumanMessage(message));

    const response = await this.model.invoke(this.history);
    const content = typeof response.content === 'string'
      ? response.content
      : JSON.stringify(response.content);

    this.history.push(new AIMessage(content));
    return content;
  }

  getHistoryLength(): number {
    return this.history.length;
  }
}

// ── Wrap as runnable for Agentspan ─────────────────────────

function createAgentRunnable() {
  const chat = new ChatWithHistory();

  const runnable = new RunnableLambda({
    func: async (input: { input: string }) => {
      const output = await chat.chat(input.input);
      return { output };
    },
  });

  // Add agentspan metadata for extraction
  (runnable as any)._agentspan = {
    model: 'openai/gpt-4o-mini',
    tools: [],
    framework: 'langchain',
  };

  return { runnable, chat };
}

async function main() {
  const turns = [
    'Hi! My name is Alex and I work in data science.',
    "I'm learning LangGraph for building AI agents.",
    "What's my name and what am I learning about?",
  ];

  // ── Run on agentspan ──────────────────────────────────────
  const runtime = new AgentRuntime();
  const { runnable, chat } = createAgentRunnable();

  try {
    for (let i = 0; i < turns.length; i++) {
      console.log(`\n--- Turn ${i + 1} ---`);
      console.log(`User: ${turns[i]}`);
      const result = await runtime.run(runnable, turns[i]);
      console.log(`Status: ${result.status}`);
      result.printResult();
      console.log(`(History: ${chat.getHistoryLength()} messages)`);
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
