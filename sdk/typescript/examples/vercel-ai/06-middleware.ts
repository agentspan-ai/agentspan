/**
 * Vercel AI SDK -- Middleware + Agentspan Guardrails
 *
 * Demonstrates combining Vercel AI SDK middleware patterns with
 * Agentspan guardrails for input/output validation.
 *
 * In production you would use:
 *   import { generateText, experimental_wrapLanguageModel } from 'ai';
 *   const wrappedModel = experimental_wrapLanguageModel({ model, middleware });
 */

import { AgentRuntime, Agent } from '../../src/index.js';

// -- Mock middleware that logs and validates --
function applyMiddleware(
  input: string,
): { allowed: boolean; reason?: string; sanitized: string } {
  // Check for PII patterns
  const piiPatterns = [
    /\b\d{3}-\d{2}-\d{4}\b/,  // SSN
    /\b\d{16}\b/,               // Credit card
  ];

  for (const pattern of piiPatterns) {
    if (pattern.test(input)) {
      return {
        allowed: false,
        reason: 'Input contains potential PII. Request blocked by middleware.',
        sanitized: input,
      };
    }
  }

  // Sanitize: strip excessive whitespace
  const sanitized = input.replace(/\s+/g, ' ').trim();
  return { allowed: true, sanitized };
}

// -- Mock Vercel AI SDK agent with middleware --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    // Apply middleware before processing
    const check = applyMiddleware(options.prompt);

    if (!check.allowed) {
      return {
        text: `[BLOCKED] ${check.reason}`,
        toolCalls: [],
        finishReason: 'stop' as const,
      };
    }

    return {
      text:
        `[Middleware: input sanitized, ${check.sanitized.length} chars]\n\n` +
        `Response: Your question about "${check.sanitized.slice(0, 50)}..." has been processed. ` +
        `All middleware checks passed and guardrails are satisfied.`,
      toolCalls: [],
      finishReason: 'stop' as const,
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  id: 'vercel_middleware_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  // Test 1: Normal request (passes middleware)
  console.log('=== Test 1: Normal request ===');
  let result = await runtime.run(
    vercelAgent,
    'Explain how middleware works in AI agent pipelines.',
  );
  console.log('Status:', result.status);
  result.printResult();

  // Test 2: Request with PII (blocked by middleware)
  console.log('\n=== Test 2: Request with PII (should be blocked) ===');
  result = await runtime.run(
    vercelAgent,
    'My social security number is 123-45-6789. Can you verify it?',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
