/**
 * Guardrails — block responses containing email addresses.
 */

import { Agent, AgentRuntime, RegexGuardrail } from '../../src/index.js';
import { llmModel } from '../settings.js';

export const agent = new Agent({
  name: 'safe_bot',
  model: llmModel,
  instructions: 'Answer questions. Never include email addresses in your response.',
  guardrails: [
    new RegexGuardrail({
      name: 'no_emails',
      patterns: ['[\\w.+-]+@[\\w-]+\\.[\\w.-]+'],
      message: 'Remove email addresses from your response.',
      onFail: 'retry',
    }),
  ],
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'How do I contact support?');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/quickstart --agents safe_bot
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

export const prompt = 'How do I contact support?';

if (process.argv[1]?.includes('04-guardrails')) {
  main().catch(console.error);
}
