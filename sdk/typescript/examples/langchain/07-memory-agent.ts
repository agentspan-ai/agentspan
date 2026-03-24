/**
 * Memory Agent -- agent with persistent user profile memory and tools.
 *
 * Demonstrates:
 *   - In-memory user profile store keyed by userId
 *   - DynamicStructuredTool for saving and retrieving user preferences
 *   - ChatOpenAI with tool-calling to manage user profiles
 *   - Running via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── In-memory user profile store ─────────────────────────

const userProfiles: Record<string, Record<string, string>> = {};

// ── Tool definitions ─────────────────────────────────────

const savePreferenceTool = new DynamicStructuredTool({
  name: 'save_preference',
  description: 'Save a user preference to their profile. Use this when the user shares personal information like name, language preference, timezone, etc.',
  schema: z.object({
    userId: z.string().describe('The user ID'),
    key: z.string().describe('Preference key (e.g. "name", "language", "timezone")'),
    value: z.string().describe('Preference value'),
  }),
  func: async ({ userId, key, value }) => {
    if (!userProfiles[userId]) userProfiles[userId] = {};
    userProfiles[userId][key] = value;
    return `Saved preference for ${userId}: ${key} = ${value}`;
  },
});

const getPreferenceTool = new DynamicStructuredTool({
  name: 'get_preference',
  description: 'Get a specific preference for a user.',
  schema: z.object({
    userId: z.string().describe('The user ID'),
    key: z.string().describe('Preference key to look up'),
  }),
  func: async ({ userId, key }) => {
    const profile = userProfiles[userId];
    if (!profile || !profile[key]) {
      return `No preference '${key}' found for user ${userId}`;
    }
    return `User ${userId} preference '${key}': ${profile[key]}`;
  },
});

const getFullProfileTool = new DynamicStructuredTool({
  name: 'get_full_profile',
  description: 'Get the full profile for a user with all saved preferences.',
  schema: z.object({
    userId: z.string().describe('The user ID'),
  }),
  func: async ({ userId }) => {
    const profile = userProfiles[userId];
    if (!profile || Object.keys(profile).length === 0) {
      return `No profile data found for user ${userId}`;
    }
    const items = Object.entries(profile).map(([k, v]) => `  ${k}: ${v}`).join('\n');
    return `Profile for ${userId}:\n${items}`;
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [savePreferenceTool, getPreferenceTool, getFullProfileTool];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runMemoryAgent(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage(
      'You are a personalized assistant that remembers user preferences. ' +
      'When users share personal information, save it using save_preference. ' +
      'When asked about what you know, use get_full_profile. ' +
      'Always be helpful and reference saved preferences in your responses.'
    ),
    new HumanMessage(prompt),
  ];

  for (let i = 0; i < 8; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    for (const tc of toolCalls) {
      const tool = toolMap[tc.name];
      if (tool) {
        const result = await (tool as any).invoke(tc.args);
        messages.push(new ToolMessage({ content: String(result), tool_call_id: tc.id! }));
      }
    }
  }

  return 'Agent reached maximum iterations.';
}

// ── Wrap for Agentspan ───────────────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runMemoryAgent(input.input);
    return { output };
  },
});

// Add agentspan metadata for extraction
(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langchain',
};

async function main() {
  const runtime = new AgentRuntime();
  const userId = 'user-42';

  const interactions = [
    `My user ID is ${userId}. Please save that my name is Jordan and I prefer Python.`,
    `For user ${userId}, also save that my timezone is US/Pacific.`,
    `What do you know about user ${userId}?`,
  ];

  try {
    for (const msg of interactions) {
      console.log(`\n${'='.repeat(60)}`);
      console.log(`User: ${msg}`);
      const result = await runtime.run(agentRunnable, msg);
      console.log('Status:', result.status);
      result.printResult();
      console.log('-'.repeat(60));
    }

    // Show final profile state
    console.log('\n=== Final Profile State ===');
    console.log(JSON.stringify(userProfiles, null, 2));
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
