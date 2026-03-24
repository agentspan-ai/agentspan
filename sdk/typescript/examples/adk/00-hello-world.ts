/**
 * Minimal Google ADK Greeting Agent.
 *
 * The simplest possible ADK agent: no tools, no structured output, one turn.
 * Used to verify the ADK integration works end-to-end.
 *
 * Two execution paths:
 *   1. Native ADK — InMemoryRunner + InMemorySessionService (requires GOOGLE_API_KEY)
 *   2. Agentspan — runtime.run() passthrough (requires AGENTSPAN_SERVER_URL)
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
  instruction: 'You are a friendly greeter. Reply with a warm hello and one fun fact.',
});

// ── Path 1: Native ADK ──────────────────────────────────────────────

async function runNative() {
  console.log('=== Native ADK ===');
  const sessionService = new InMemorySessionService();
  const runner = new InMemoryRunner({ agent, appName: 'hello-world', sessionService });
  const session = await sessionService.createSession({ appName: 'hello-world', userId: 'user1' });

  const message = { role: 'user' as const, parts: [{ text: 'Say hello!' }] };

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
    const result = await runtime.run(agent, 'Say hello!');
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
