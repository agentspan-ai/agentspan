/**
 * Google ADK Agent with Streaming -- real-time event streaming.
 *
 * Demonstrates:
 *   - Streaming events from a Google ADK agent
 *   - Native path: iterating over InMemoryRunner.runAsync() events
 *   - Agentspan path: runtime.stream() with event types
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - GOOGLE_API_KEY or GOOGLE_GENAI_API_KEY for native path
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool, InMemoryRunner, InMemorySessionService } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool ─────────────────────────────────────────────────────────────

const searchDocumentation = new FunctionTool({
  name: 'search_documentation',
  description: 'Search the product documentation.',
  parameters: z.object({
    query: z.string().describe('Search query string'),
  }),
  execute: async (args: { query: string }) => {
    const docs: Record<string, { title: string; content: string }> = {
      installation: {
        title: 'Installation Guide',
        content: 'Run `npm install mypackage`. Requires Node.js 18+.',
      },
      authentication: {
        title: 'Authentication',
        content: 'Use API keys via the X-API-Key header. Keys are managed in the dashboard.',
      },
      'rate limits': {
        title: 'Rate Limiting',
        content: 'Free tier: 100 req/min. Pro: 1000 req/min. Enterprise: unlimited.',
      },
    };
    for (const [key, value] of Object.entries(docs)) {
      if (args.query.toLowerCase().includes(key)) {
        return { found: true, ...value };
      }
    }
    return { found: false, message: 'No matching documentation found.' };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

const agent = new LlmAgent({
  name: 'docs_assistant',
  model,
  instruction:
    'You are a documentation assistant. Use the search tool to find ' +
    'relevant docs and provide clear, well-formatted answers.',
  tools: [searchDocumentation],
});

// ── Path 1: Native ADK (streaming events) ───────────────────────────

async function runNative() {
  console.log('=== Native ADK (streaming events) ===');
  const sessionService = new InMemorySessionService();
  const runner = new InMemoryRunner({ agent, appName: 'streaming', sessionService });
  const session = await sessionService.createSession({ appName: 'streaming', userId: 'user1' });

  const message = { role: 'user' as const, parts: [{ text: 'How do I authenticate with the API?' }] };

  try {
    console.log('Events:');
    for await (const event of runner.runAsync({
      userId: 'user1',
      sessionId: session.id,
      newMessage: message,
    })) {
      const author = event?.author ?? 'unknown';
      const parts = event?.content?.parts ?? [];
      const textParts = parts.filter((p: any) => typeof p?.text === 'string');
      const funcParts = parts.filter((p: any) => p?.functionCall);
      const respParts = parts.filter((p: any) => p?.functionResponse);

      if (funcParts.length > 0) {
        for (const p of funcParts) {
          console.log(`  [${author}] tool_call: ${p.functionCall.name}(${JSON.stringify(p.functionCall.args)})`);
        }
      } else if (respParts.length > 0) {
        for (const p of respParts) {
          console.log(`  [${author}] tool_result: ${p.functionResponse.name} -> ${JSON.stringify(p.functionResponse.response).slice(0, 100)}`);
        }
      } else if (textParts.length > 0) {
        for (const p of textParts) {
          console.log(`  [${author}] text: ${p.text.slice(0, 150)}`);
        }
      }
    }
    console.log('\nStream complete.');
  } catch (err: any) {
    console.log('Native path error (expected without GOOGLE_API_KEY):', err.message?.slice(0, 200));
  }
}

// ── Path 2: Agentspan (streaming) ───────────────────────────────────

async function runAgentspan() {
  console.log('\n=== Agentspan (streaming) ===');
  const runtime = new AgentRuntime();
  try {
    const streamHandle = await runtime.stream(
      agent,
      'How do I authenticate with the API?',
    );
    console.log(`Workflow started: ${streamHandle.workflowId}\n`);
    console.log('Events:');

    for await (const event of streamHandle) {
      switch (event.type) {
        case 'thinking':
          console.log(`  [thinking] ${event.content}`);
          break;
        case 'tool_call':
          console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
          break;
        case 'tool_result':
          console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result).slice(0, 100)}`);
          break;
        case 'done':
          console.log(`  [done] ${JSON.stringify(event.output).slice(0, 200)}`);
          break;
        case 'error':
          console.log(`  [error] ${event.content}`);
          break;
      }
    }

    const final = await streamHandle.getResult();
    console.log(`\nStatus: ${final.status}`);
  } catch (err: any) {
    console.log('Agentspan path error:', err.message?.slice(0, 200));
  } finally {
    await runtime.shutdown();
  }
}

// ── Run ──────────────────────────────────────────────────────────────

async function main() {
  await runNative();
  await runAgentspan();
}

main().catch(console.error);
