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

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

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
    inputSchema: z.object({
      title: z.string().describe('Article title'),
      body: z.string().describe('Article body'),
    }),
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

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    const result = await runtime.run(agent, 'Write a short blog post outline about the benefits of code review. Do not publish it.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);

    // Interactive HITL alternative:
    // const runtime = new AgentRuntime();
    // try {
    // const streamHandle = await runtime.stream(
    // agent,
    // 'Write a short blog post about the benefits of code review',
    // );
    // console.log(`Execution started: ${streamHandle.executionId}\n`);

    // for await (const event of streamHandle) {
    // console.log(`event type: ${event.type} --> ${event.content}`);

    // switch (event.type) {
    // case 'thinking':
    // console.log(`  [thinking] ${event.content}`);
    // break;

    // case 'tool_call': {
    // console.log(`  [tool_call] ${event.toolName}`);
    // if (event.args) {
    // const args = event.args as Record<string, string>;
    // if (args.title) {
    // console.log(`    Title: ${args.title}`);
    // }
    // if (args.body) {
    // const preview =
    // args.body.length > 200
    // ? args.body.slice(0, 200) + '...'
    // : args.body;
    // console.log(`    Body:  ${preview}`);
    // }
    // }
    // break;
    // }

    // case 'guardrail_fail': {
    // console.log(`  [guardrail failed] ${event.guardrailName}`);
    // if (event.args) {
    // const args = event.args as Record<string, string>;
    // if (args.title) {
    // console.log(`    Title: ${args.title}`);
    // }
    // if (args.body) {
    // const preview =
    // args.body.length > 200
    // ? args.body.slice(0, 200) + '...'
    // : args.body;
    // console.log(`    Body:  ${preview}`);
    // }
    // }
    // break;
    // }

    // case 'tool_result':
    // console.log(
    // `  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result)}`,
    // );
    // break;

    // case 'waiting':
    // console.log(`\n--- Editorial Review Required ---`);
    // console.log('  [a] Approve and publish');
    // console.log('  [r] Reject entirely');
    // console.log('  [f] Provide feedback for revision');
    // console.log();
    // // Auto-approve since we can't do interactive stdin
    // console.log('  Auto-approving for demo...');
    // await streamHandle.approve();
    // console.log('  Approved for publication!\n');
    // break;

    // case 'error':
    // console.log(`  [error] ${event.content}`);
    // break;

    // case 'done':
    // console.log(`\n  [done] ${JSON.stringify(event.output)}`);
    // break;
    // }
    // }

    // // Access the structured result after streaming
    // const final = await streamHandle.getResult();
    // console.log(`\nTool calls made: ${final.toolCalls.length}`);
    // console.log(`Status: ${final.status}`);
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('09b-hitl-with-feedback.ts') || process.argv[1]?.endsWith('09b-hitl-with-feedback.js')) {
  main().catch(console.error);
}
