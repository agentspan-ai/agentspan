/**
 * Google ADK Agent with Generation Config -- temperature and output control.
 *
 * Demonstrates:
 *   - Using generateContentConfig for model tuning
 *   - Low temperature for factual/deterministic responses
 *   - High temperature for creative responses
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - GOOGLE_API_KEY or GOOGLE_GENAI_API_KEY for native path
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, InMemoryRunner, InMemorySessionService } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Precise agent -- low temperature for factual responses ──────────

const factualAgent = new LlmAgent({
  name: 'fact_checker',
  model,
  instruction:
    'You are a precise fact-checker. Provide accurate, well-sourced ' +
    'answers. Be concise and avoid speculation.',
  generateContentConfig: {
    temperature: 0.1,
  },
});

// ── Creative agent -- high temperature for creative writing ─────────

const creativeAgent = new LlmAgent({
  name: 'storyteller',
  model,
  instruction:
    'You are an imaginative storyteller. Create vivid, engaging ' +
    'narratives with rich descriptions and unexpected twists.',
  generateContentConfig: {
    temperature: 0.9,
  },
});

// ── Helper: run a single agent via InMemoryRunner ───────────────────

async function runAgentNative(agent: any, prompt: string, appName: string): Promise<string> {
  const sessionService = new InMemorySessionService();
  const runner = new InMemoryRunner({ agent, appName, sessionService });
  const session = await sessionService.createSession({ appName, userId: 'user1' });

  const message = { role: 'user' as const, parts: [{ text: prompt }] };
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
  return lastText;
}

// ── Path 1: Native ADK ──────────────────────────────────────────────

async function runNative() {
  console.log('=== Native ADK ===');

  try {
    console.log('\n--- Factual Agent (temp=0.1) ---');
    const factResult = await runAgentNative(factualAgent, 'What is the speed of light in a vacuum?', 'gen-config-fact');
    console.log('Response:', factResult || '(no response)');

    console.log('\n--- Creative Agent (temp=0.9) ---');
    const creativeResult = await runAgentNative(
      creativeAgent,
      'Write a two-sentence story about a cat who discovered a hidden library.',
      'gen-config-creative',
    );
    console.log('Response:', creativeResult || '(no response)');
  } catch (err: any) {
    console.log('Native path error (expected without GOOGLE_API_KEY):', err.message?.slice(0, 200));
  }
}

// ── Path 2: Agentspan ───────────────────────────────────────────────

async function runAgentspan() {
  console.log('\n=== Agentspan ===');
  const runtime = new AgentRuntime();
  try {
    console.log('\n--- Factual Agent (temp=0.1) ---');
    const factResult = await runtime.run(factualAgent, 'What is the speed of light in a vacuum?');
    console.log(`Status: ${factResult.status}`);
    factResult.printResult();

    console.log('\n--- Creative Agent (temp=0.9) ---');
    const creativeResult = await runtime.run(
      creativeAgent,
      'Write a two-sentence story about a cat who discovered a hidden library.',
    );
    console.log(`Status: ${creativeResult.status}`);
    creativeResult.printResult();
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
