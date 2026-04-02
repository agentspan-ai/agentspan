/**
 * Human-in-the-Loop with Streaming — Console Interactive.
 *
 * Streams agent events in real time via SSE. When the agent pauses for
 * human approval, the user is prompted in the console to approve, reject,
 * or provide feedback — all through the AgentStream object.
 *
 * Use case: an ops agent that can restart services (safe) and delete data
 * (dangerous, requires approval). The operator watches the agent think
 * in real time and intervenes only for destructive actions.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

const checkService = tool(
  async (args: { serviceName: string }) => {
    return { service: args.serviceName, status: 'unhealthy', uptime: '0m' };
  },
  {
    name: 'check_service',
    description: 'Check the health of a service.',
    inputSchema: z.object({
      serviceName: z.string().describe('Name of the service to check'),
    }),
  },
);

const restartService = tool(
  async (args: { serviceName: string }) => {
    return { service: args.serviceName, status: 'restarted', new_uptime: '0m' };
  },
  {
    name: 'restart_service',
    description: 'Restart a service. Safe operation, no approval needed.',
    inputSchema: z.object({
      serviceName: z.string().describe('Name of the service to restart'),
    }),
  },
);

const deleteServiceData = tool(
  async (args: { serviceName: string; dataType: string }) => {
    return {
      service: args.serviceName,
      data_type: args.dataType,
      status: 'deleted',
    };
  },
  {
    name: 'delete_service_data',
    description: 'Delete service data. Destructive — requires human approval.',
    inputSchema: z.object({
      serviceName: z.string().describe('Name of the service'),
      dataType: z.string().describe('Type of data to delete'),
    }),
    approvalRequired: true,
  },
);

export const agent = new Agent({
  name: 'ops_agent',
  model: llmModel,
  tools: [checkService, restartService, deleteServiceData],
  instructions:
    'You are an operations assistant. You can check, restart, and manage services. ' +
    'If a service is unhealthy, check it first, then restart it. Only suggest ' +
    'deleting data if explicitly asked.',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'The payments service is down. Check it and restart it.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents ops_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);

    // Interactive streaming alternative:
    // // stream() starts the workflow and returns an AgentStream —
    // // iterable for events, with HITL controls built in.
    // const streamHandle = await runtime.stream(
    // agent,
    // 'The payments service is down. Check it, restart it, and clear its stale cache data.',
    // );
    // console.log(`Execution started: ${streamHandle.executionId}\n`);

    // for await (const event of streamHandle) {
    // switch (event.type) {
    // case 'thinking':
    // console.log(`  [thinking] ${event.content}`);
    // break;

    // case 'tool_call':
    // console.log(
    // `  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`,
    // );
    // break;

    // case 'tool_result':
    // console.log(
    // `  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result)}`,
    // );
    // break;

    // case 'waiting':
    // console.log(`\n--- Approval required ---`);
    // // Auto-approve since we can't do interactive stdin
    // console.log('  Auto-approving for demo...');
    // await streamHandle.approve();
    // console.log('  Approved!\n');
    // break;

    // case 'guardrail_pass':
    // console.log(`  [guardrail] ${event.guardrailName} passed`);
    // break;

    // case 'guardrail_fail':
    // console.log(
    // `  [guardrail] ${event.guardrailName} FAILED: ${event.content}`,
    // );
    // break;

    // case 'error':
    // console.log(`  [error] ${event.content}`);
    // break;

    // case 'done':
    // console.log(`\n  [done] ${JSON.stringify(event.output)}`);
    // break;
    // }
    // }

    // // After iteration, the full result is available
    // const final = await streamHandle.getResult();
    // console.log(`\nTool calls made: ${final.toolCalls.length}`);
    // console.log(`Status: ${final.status}`);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('09c-hitl-streaming.ts') || process.argv[1]?.endsWith('09c-hitl-streaming.js')) {
  main().catch(console.error);
}
