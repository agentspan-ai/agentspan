/**
 * 06 - Human-in-the-Loop (HITL)
 *
 * Demonstrates a tool with approvalRequired: true.
 * Uses stream.approve(), stream.reject(), and stream.send().
 */

import {
  Agent,
  AgentRuntime,
  EventTypes,
  tool,
} from '../src/index.js';

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

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(publishingAgent);
    await runtime.serve(publishingAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const agentStream = await runtime.stream(
    // publishingAgent,
    // 'Write a short article about TypeScript and publish it.',
    // );

    // let attempt = 0;

    // for await (const event of agentStream) {
    // if (event.type === EventTypes.WAITING) {
    // attempt++;
    // console.log(`\n--- HITL: Approval required (attempt ${attempt}) ---`);

    // if (attempt === 1) {
          // First: send feedback
    // console.log('Sending feedback...');
    // await agentStream.send('Please make the title more descriptive.');
    // } else if (attempt === 2) {
          // Second: reject
    // console.log('Rejecting...');
    // await agentStream.reject('Title still needs improvement.');
    // } else {
          // Third: approve
    // console.log('Approving!');
    // await agentStream.approve();
    // }
    // } else if (event.type === EventTypes.DONE) {
    // console.log('\nDone!');
    // } else if (event.type === EventTypes.MESSAGE) {
    // console.log(`[message] ${(event.content ?? '').slice(0, 100)}`);
    // }
    // }

    // const result = await agentStream.getResult();
    // result.printResult();

    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('06-hitl.ts') || process.argv[1]?.endsWith('06-hitl.js')) {

  main().catch(console.error);
}
