/**
 * Vercel AI SDK -- Stop Conditions + Agentspan Termination
 *
 * Demonstrates using stopWhen conditions with a Vercel AI SDK agent
 * and Agentspan's termination system. The agent stops when:
 * - A maximum number of steps is reached
 * - A specific phrase is detected in the output
 * - The agent signals completion
 *
 * In production you would use:
 *   import { generateText } from 'ai';
 *   const result = await generateText({ model, tools, maxSteps: 10, stopSequences: [...] });
 */

import { AgentRuntime } from '../../src/index.js';

// -- Configuration --
const MAX_STEPS = 5;
const STOP_PHRASE = 'TASK_COMPLETE';

// -- Mock Vercel AI SDK agent with iterative processing --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    // Simulate a multi-step process that eventually completes
    const steps: string[] = [];

    for (let i = 1; i <= MAX_STEPS; i++) {
      steps.push(`Step ${i}: Processing "${options.prompt.slice(0, 30)}..." -- analyzing data`);

      // Simulate early completion on step 3
      if (i === 3) {
        steps.push(`Step ${i}: Analysis complete. ${STOP_PHRASE}`);
        break;
      }
    }

    const text = steps.join('\n');
    const finished = text.includes(STOP_PHRASE);

    return {
      text: finished
        ? text + '\n\nFinal Answer: The analysis has been completed successfully.'
        : text + '\n\n[Stopped: maximum steps reached]',
      toolCalls: [],
      finishReason: (finished ? 'stop' : 'length') as 'stop' | 'length',
      usage: { promptTokens: 100, completionTokens: steps.length * 20 },
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  id: 'vercel_stop_conditions_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  console.log(`Running with stop conditions (max ${MAX_STEPS} steps, stop on "${STOP_PHRASE}")...\n`);
  const result = await runtime.run(
    vercelAgent,
    'Analyze the market trends for AI infrastructure companies.',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
