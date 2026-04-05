/**
 * Human-in-the-Loop with Custom Feedback.
 *
 * Demonstrates the general-purpose respond() API. Instead of a binary
 * approve/reject, the human can send arbitrary feedback that the LLM
 * processes on its next iteration.
 *
 * Use case: a content-publishing agent writes a blog post, and a human
 * editor can approve, reject, or provide revision notes. The agent
 * incorporates the feedback and tries again.
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

const publishArticle = tool(
  async (args: { title: string; body: string }) => {
    return {
      status: 'published',
      title: args.title,
      url: `/blog/${args.title.toLowerCase().replace(/ /g, '-')}`,
    };
  },
  {
    name: 'publish_article',
    description: 'Publish an article to the blog. Requires editorial approval.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Article title' },
        body: { type: 'string', description: 'Article body' },
      },
      required: ['title', 'body'],
    },
    approvalRequired: true,
  },
);

export const agent = new Agent({
  name: 'writer',
  model: llmModel,
  tools: [publishArticle],
  instructions:
    'You are a blog writer. When asked to write about a topic, draft an article ' +
    'and publish it using the publish_article tool. If you receive editorial ' +
    'feedback, revise the article and try publishing again.',
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
      'Write a short blog post about the benefits of code review',
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
    // const result = await runtime.run(agent, 'Write a short blog post outline about the benefits of code review. Do not publish it.');
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
