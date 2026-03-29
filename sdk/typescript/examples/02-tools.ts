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
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

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
    inputSchema: z.object({
      city: z.string().describe('The city to get weather for'),
    }),
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
    inputSchema: z.object({
      expression: z.string().describe('The math expression to evaluate'),
    }),
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
    inputSchema: z.object({
      to: z.string().describe('Recipient email address'),
      subject: z.string().describe('Email subject'),
      body: z.string().describe('Email body'),
    }),
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

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const streamHandle = await runtime.stream(
    // agent,
    // 'send email to developer@orkes.io with current weather details in SF',
    // );
    // console.log(`Workflow started: ${streamHandle.workflowId}\n`);

    // for await (const event of streamHandle) {
    // switch (event.type) {
    // case 'thinking':
    // console.log(`  [thinking] ${event.content}`);
    // break;

    // case 'tool_call':
    // console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
    // break;

    // case 'tool_result':
    // console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result)}`);
    // break;

    // case 'waiting':
    // console.log(`\n--- Human approval required for send_email ---`);
    // // In a real application you'd prompt for user input.
    // // Auto-approve for this example:
    // console.log('  Auto-approving for demo...');
    // await streamHandle.approve();
    // console.log('  Approved!\n');
    // break;

    // case 'error':
    // console.log(`  [error] ${event.content}`);
    // break;

    // case 'done':
    // console.log(`\nResult: ${JSON.stringify(event.output)}`);
    // break;
    // }
    // }

    // const final = await streamHandle.getResult();
    // console.log(`\nTool calls: ${final.toolCalls.length}`);
    // console.log(`Status: ${final.status}`);
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('02-tools.ts') || process.argv[1]?.endsWith('02-tools.js')) {
  main().catch(console.error);
}
