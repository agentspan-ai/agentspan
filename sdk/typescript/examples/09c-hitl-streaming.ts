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

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

const checkService = tool(
  async (args: { serviceName: string }) => {
    return { service: args.serviceName, status: 'unhealthy', uptime: '0m' };
  },
  {
    name: 'check_service',
    description: 'Check the health of a service.',
    inputSchema: {
      type: 'object',
      properties: {
        serviceName: { type: 'string', description: 'Name of the service to check' },
      },
      required: ['serviceName'],
    },
  },
);

const restartService = tool(
  async (args: { serviceName: string }) => {
    return { service: args.serviceName, status: 'restarted', new_uptime: '0m' };
  },
  {
    name: 'restart_service',
    description: 'Restart a service. Safe operation, no approval needed.',
    inputSchema: {
      type: 'object',
      properties: {
        serviceName: { type: 'string', description: 'Name of the service to restart' },
      },
      required: ['serviceName'],
    },
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
    inputSchema: {
      type: 'object',
      properties: {
        serviceName: { type: 'string', description: 'Name of the service' },
        dataType: { type: 'string', description: 'Type of data to delete' },
      },
      required: ['serviceName', 'dataType'],
    },
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

async function promptHuman(
  rl: readline.Interface,
  pendingTool: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const schema = (pendingTool.response_schema ?? {}) as Record<string, unknown>;
  const props = (schema.properties ?? {}) as Record<string, Record<string, unknown>>;
  const response: Record<string, unknown> = {};
  for (const [field, fs] of Object.entries(props)) {
    const desc = (fs.description || fs.title || field) as string;
    if (fs.type === 'boolean') {
      const val = await rl.question(`  ${desc} (y/n): `);
      response[field] = ['y', 'yes'].includes(val.trim().toLowerCase());
    } else {
      response[field] = await rl.question(`  ${desc}: `);
    }
  }
  return response;
}

async function main() {
  const rl = readline.createInterface({ input: stdin, output: stdout });
  const runtime = new AgentRuntime();
  try {
    const handle = await runtime.start(
      agent,
      'The payments service is down. Check it, restart it, and clear its stale cache data.',
    );
    console.log(`Started: ${handle.executionId}\n`);

    for await (const event of handle.stream()) {
      if (event.type === 'thinking') {
        console.log(`  [thinking] ${event.content}`);
      } else if (event.type === 'tool_call') {
        console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
      } else if (event.type === 'tool_result') {
        console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result).slice(0, 100)}`);
      } else if (event.type === 'waiting') {
        const status = await handle.getStatus();
        const pt = (status.pendingTool ?? {}) as Record<string, unknown>;
        console.log('\n--- Human input required ---');
        const response = await promptHuman(rl, pt);
        await handle.respond(response);
        console.log();
      } else if (event.type === 'done') {
        console.log(`\nDone: ${JSON.stringify(event.output)}`);
      }
    }

    // Non-interactive alternative (no HITL, will block on human tasks):
    // const result = await runtime.run(agent, 'The payments service is down. Check it and restart it.');
    // result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    rl.close();
    await runtime.shutdown();
  }
}

main().catch(console.error);
