/**
 * Vercel AI SDK -- Middleware
 *
 * Demonstrates using wrapLanguageModel to apply middleware that
 * intercepts and transforms LLM calls. The middleware logs requests
 * and can block calls containing PII patterns.
 *
 * Path 1: Native generateText with wrapped model.
 * Path 2: Agentspan passthrough with the same wrapped model.
 */

import {
  generateText,
  wrapLanguageModel,
  type LanguageModelV1Middleware,
} from 'ai';
import { openai } from '@ai-sdk/openai';
import { AgentRuntime } from '../../src/index.js';

// ── PII detection patterns ───────────────────────────────
const PII_PATTERNS = [
  /\b\d{3}-\d{2}-\d{4}\b/,   // SSN
  /\b\d{16}\b/,                // Credit card
  /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/, // Email
];

function containsPII(text: string): boolean {
  return PII_PATTERNS.some(p => p.test(text));
}

// ── Middleware: logging + PII guard ──────────────────────
const loggingMiddleware: LanguageModelV1Middleware = {
  transformParams: async ({ type, params }) => {
    console.log(`  [middleware] ${type} call, ${params.prompt.length} prompt parts`);

    // Check for PII in user messages
    for (const part of params.prompt) {
      if (part.role === 'user') {
        for (const content of part.content) {
          if (content.type === 'text' && containsPII(content.text)) {
            console.log('  [middleware] PII detected! Sanitizing input...');
            // Replace PII with redacted placeholder
            content.text = content.text
              .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[REDACTED-SSN]')
              .replace(/\b\d{16}\b/g, '[REDACTED-CC]');
          }
        }
      }
    }
    return params;
  },
};

// ── Wrapped model ────────────────────────────────────────
const baseModel = openai('gpt-4o-mini');
const wrappedModel = wrapLanguageModel({
  model: baseModel,
  middleware: loggingMiddleware,
});

// ── Test prompts ─────────────────────────────────────────
const prompts = [
  {
    label: 'Normal request',
    text: 'Explain how middleware works in AI agent pipelines.',
  },
  {
    label: 'Request with PII (should be sanitized)',
    text: 'My social security number is 123-45-6789. Can you verify it?',
  },
];

// ── Path 1: Native Vercel AI SDK with middleware ─────────
for (const { label, text } of prompts) {
  console.log(`\n=== Native: ${label} ===`);
  const result = await generateText({
    model: wrappedModel,
    prompt: text,
  });
  console.log('Output:', result.text.slice(0, 200) + (result.text.length > 200 ? '...' : ''));
}

// ── Path 2: Agentspan passthrough ────────────────────────
const vercelAgent = {
  id: 'middleware_agent',
  tools: {},
  generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
    const result = await generateText({
      model: wrappedModel,
      prompt: opts.prompt,
    });
    return {
      text: result.text,
      toolCalls: [],
      toolResults: [],
      finishReason: result.finishReason,
    };
  },
  stream: async function* () { yield { type: 'finish' as const }; },
};

console.log('\n\n=== Agentspan Passthrough ===');
const runtime = new AgentRuntime();
try {
  for (const { label, text } of prompts) {
    console.log(`\n--- ${label} ---`);
    const agentspanResult = await runtime.run(vercelAgent, text);
    console.log('Output:', JSON.stringify(agentspanResult.output).slice(0, 200));
    console.log('Status:', agentspanResult.status);
  }
} finally {
  await runtime.shutdown();
}
