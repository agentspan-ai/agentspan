/**
 * 05 - Streaming
 *
 * Demonstrates runtime.stream() with for-await-of loop
 * and event type switching.
 */

import {
  Agent,
  AgentRuntime,
  EventTypes,
} from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

const agent = new Agent({
  name: 'streaming_agent',
  model: MODEL,
  instructions: 'Answer the question thoroughly.',
});

async function main() {
  const runtime = new AgentRuntime();

  const agentStream = await runtime.stream(
    agent,
    'Explain how quantum computers work.',
  );

  console.log(`Workflow: ${agentStream.workflowId}\n`);

  for await (const event of agentStream) {
    switch (event.type) {
      case EventTypes.THINKING:
        console.log(`[thinking] ${(event.content ?? '').slice(0, 80)}...`);
        break;

      case EventTypes.TOOL_CALL:
        console.log(`[tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
        break;

      case EventTypes.TOOL_RESULT:
        console.log(`[tool_result] ${event.toolName} -> ${String(event.result).slice(0, 80)}`);
        break;

      case EventTypes.HANDOFF:
        console.log(`[handoff] -> ${event.target}`);
        break;

      case EventTypes.GUARDRAIL_PASS:
        console.log(`[guardrail_pass] ${event.guardrailName}`);
        break;

      case EventTypes.GUARDRAIL_FAIL:
        console.log(`[guardrail_fail] ${event.guardrailName}: ${event.content}`);
        break;

      case EventTypes.MESSAGE:
        console.log(`[message] ${(event.content ?? '').slice(0, 120)}`);
        break;

      case EventTypes.WAITING:
        console.log('[waiting] Approval required');
        break;

      case EventTypes.ERROR:
        console.log(`[error] ${event.content}`);
        break;

      case EventTypes.DONE:
        console.log('[done] Stream complete');
        break;
    }
  }

  const result = await agentStream.getResult();
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
