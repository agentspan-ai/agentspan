/**
 * Tools — multiple tools, async, approval.
 *
 * Demonstrates:
 *   - Multiple tool() functions
 *   - Approval-required tools (human-in-the-loop)
 *   - How tools become Conductor task definitions
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import type { AgentHandle } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

const getWeather = tool(
  async (args: { city: string }) => {
    const weatherData: Record<string, { temp: number; condition: string }> = {
      'new york': { temp: 72, condition: 'Partly Cloudy' },
      'san francisco': { temp: 58, condition: 'Foggy' },
      'miami': { temp: 85, condition: 'Sunny' },
    };
    const data = weatherData[args.city.toLowerCase()] ?? { temp: 70, condition: 'Clear' };
    return { city: args.city, temperature_f: data.temp, condition: data.condition };
  },
  {
    name: 'get_weather',
    description: 'Get current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'The city to get weather for' },
      },
      required: ['city'],
    },
  },
);

const calculate = tool(
  async (args: { expression: string }) => {
    const safeBuiltins: Record<string, unknown> = {
      abs: Math.abs,
      round: Math.round,
      min: Math.min,
      max: Math.max,
      sqrt: Math.sqrt,
      pow: Math.pow,
      pi: Math.PI,
      e: Math.E,
    };
    try {
      // Simple expression evaluator (demo only — not production-safe)
      const fn = new Function(
        ...Object.keys(safeBuiltins),
        `return (${args.expression});`,
      );
      const result = fn(...Object.values(safeBuiltins));
      return { expression: args.expression, result };
    } catch (e: unknown) {
      return { expression: args.expression, error: String(e) };
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a math expression.',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'The math expression to evaluate' },
      },
      required: ['expression'],
    },
  },
);

const sendEmail = tool(
  async (args: { to: string; subject: string; body: string }) => {
    // In production, this would actually send an email
    return { status: 'sent', to: args.to, subject: args.subject };
  },
  {
    name: 'send_email',
    description: 'Send an email.',
    inputSchema: {
      type: 'object',
      properties: {
        to: { type: 'string', description: 'Recipient email address' },
        subject: { type: 'string', description: 'Email subject' },
        body: { type: 'string', description: 'Email body' },
      },
      required: ['to', 'subject', 'body'],
    },
    approvalRequired: true,
    timeoutSeconds: 60,
  },
);

export const agent = new Agent({
  name: 'tool_demo_agent',
  model: llmModel,
  tools: [getWeather, calculate, sendEmail],
  instructions:
    'You are a helpful assistant with access to weather, calculator, and email tools.',
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

const rl = readline.createInterface({ input: stdin, output: stdout });
const runtime = new AgentRuntime();
try {
  const handle = await runtime.start(
    agent,
    'send email to developer@orkes.io with current weather details in SF',
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
  // const result = await runtime.run(agent, 'What is the weather in San Francisco?');
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
