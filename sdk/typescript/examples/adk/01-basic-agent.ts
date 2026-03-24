/**
 * Basic Google ADK Agent -- simplest possible agent with instructions.
 *
 * Demonstrates:
 *   - Defining an agent using Google's Agent Development Kit (ADK)
 *   - Running via native InMemoryRunner or Agentspan passthrough
 *   - The runtime serializes the ADK agent and the server normalizes it
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - GOOGLE_API_KEY or GOOGLE_GENAI_API_KEY for native path
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, InMemoryRunner, InMemorySessionService } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

const agent = new LlmAgent({
  name: 'greeter',
  model,
  instruction: 'You are a friendly assistant. Keep your responses concise and helpful.',
});

// ── Path 1: Native ADK ──────────────────────────────────────────────

async function runNative() {
  console.log('=== Native ADK ===');
  const sessionService = new InMemorySessionService();
  const runner = new InMemoryRunner({ agent, appName: 'basic-agent', sessionService });
  const session = await sessionService.createSession({ appName: 'basic-agent', userId: 'user1' });

  const message = { role: 'user' as const, parts: [{ text: 'Say hello and tell me a fun fact about machine learning.' }] };

  try {
    let lastText = '';
    for await (const event of runner.runAsync({
      userId: 'user1',
      sessionId: session.id,
      newMessage: message,
    })) {
      const parts = event?.content?.parts;
      if (Array.isArray(parts)) {
        for (const part of parts) {
          if (typeof part?.text === 'string') lastText = part.text;
        }
      }
    }
    console.log('Response:', lastText || '(no response)');
  } catch (err: any) {
    console.log('Native path error (expected without GOOGLE_API_KEY):', err.message?.slice(0, 200));
  }
}

// ── Path 2: Agentspan ───────────────────────────────────────────────

async function runAgentspan() {
  console.log('\n=== Agentspan ===');
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      'Say hello and tell me a fun fact about machine learning.',
    );
    console.log(`Status: ${result.status}`);
    result.printResult();
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
