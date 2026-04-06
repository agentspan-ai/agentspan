/**
 * 06 - Human-in-the-Loop (HITL)
 *
 * Demonstrates a tool with approvalRequired: true.
 * Uses interactive streaming with schema-driven console prompts.
 */

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import {
  Agent,
  AgentRuntime,
  tool,
} from '@agentspan-ai/sdk';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Tool that requires human approval --
const publishArticle = tool(
  async (args: { title: string; content: string }) => {
    return { status: 'published', title: args.title };
  },
  {
    name: 'publish_article',
    description: 'Publish an article to the platform. Requires editorial approval.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string' },
        content: { type: 'string' },
      },
      required: ['title', 'content'],
    },
    approvalRequired: true,
  },
);

export const publishingAgent = new Agent({
  name: 'publisher',
  model: MODEL,
  instructions: 'Write and publish articles when asked.',
  tools: [publishArticle],
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
    publishingAgent,
    'Write a short article about TypeScript and publish it.',
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
  // const result = await runtime.run(publishingAgent, 'Write a short article outline about TypeScript, but do not publish it.');
  // result.printResult();

  // Production pattern:
  // 1. Deploy once during CI/CD:
  // await runtime.deploy(publishingAgent);
  //
  // 2. In a separate long-lived worker process:
  // await runtime.serve(publishingAgent);
} finally {
  rl.close();
  await runtime.shutdown();
}
