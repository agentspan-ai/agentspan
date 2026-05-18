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

import { Agent, AgentRuntime, EventTypes } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

export const agent = new Agent({
  name: 'haiku_writer',
  model: llmModel,
  instructions: 'You are a haiku poet. Write a single haiku.',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Write a haiku about Python programming');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents haiku_writer
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);

    // Streaming alternative:
    // console.log('Streaming agent execution:');
    // console.log('-'.repeat(40));
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

main().catch(console.error);
