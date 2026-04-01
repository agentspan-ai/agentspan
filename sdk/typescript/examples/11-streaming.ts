/**
 * 11 - Streaming — real-time events.
 *
 * Demonstrates streaming agent execution events. The runtime.stream() method
 * returns an async iterable that yields events as the agent executes,
 * allowing real-time monitoring.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, EventTypes } from '../src/index.js';
import { llmModel } from './settings.js';

export const agent = new Agent({
  name: 'haiku_writer',
  model: llmModel,
  instructions: 'You are a haiku poet. Write a single haiku.',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    const result = await runtime.run(agent, 'Write a haiku about Python programming');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);

    // Streaming alternative:
    // console.log('Streaming agent execution:');
    // console.log('-'.repeat(40));
    // const runtime = new AgentRuntime();
    // try {
    // const agentStream = await runtime.stream(
    // agent,
    // 'Write a haiku about Python programming',
    // );

    // console.log(`Execution: ${agentStream.executionId}\n`);

    // for await (const event of agentStream) {
    // switch (event.type) {
    // case EventTypes.DONE:
    // console.log(`\nResult: ${JSON.stringify(event.output)}`);
    // console.log(`Execution: ${agentStream.executionId}`);
    // break;

    // case EventTypes.WAITING:
    // console.log('[Waiting...]');
    // break;

    // case EventTypes.ERROR:
    // console.log(`[Error: ${event.content}]`);
    // break;

    // case EventTypes.THINKING:
    // console.log(`[thinking] ${(event.content ?? '').slice(0, 80)}...`);
    // break;

    // case EventTypes.TOOL_CALL:
    // console.log(`[tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
    // break;

    // case EventTypes.TOOL_RESULT:
    // console.log(`[tool_result] ${event.toolName} -> ${String(event.result).slice(0, 80)}`);
    // break;

    // case EventTypes.HANDOFF:
    // console.log(`[handoff] -> ${event.target}`);
    // break;

    // case EventTypes.GUARDRAIL_PASS:
    // console.log(`[guardrail_pass] ${event.guardrailName}`);
    // break;

    // case EventTypes.GUARDRAIL_FAIL:
    // console.log(`[guardrail_fail] ${event.guardrailName}: ${event.content}`);
    // break;

    // case EventTypes.MESSAGE:
    // console.log(`[message] ${(event.content ?? '').slice(0, 120)}`);
    // break;
    // }
    // }

    // const result = await agentStream.getResult();
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('11-streaming.ts') || process.argv[1]?.endsWith('11-streaming.js')) {
  main().catch(console.error);
}
