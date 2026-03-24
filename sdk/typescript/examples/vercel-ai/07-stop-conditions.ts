/**
 * Vercel AI SDK -- Stop Conditions
 *
 * Demonstrates controlling when a multi-step agent stops:
 * - maxSteps: Hard limit on number of LLM calls
 * - stopSequences: Stop when specific text is generated
 * - Tool-based termination: Agent stops after getting enough data
 *
 * Path 1: Native generateText with maxSteps and step tracking.
 * Path 2: Agentspan passthrough with the same stop conditions.
 */

import { generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');

// ── Tools ────────────────────────────────────────────────
let analysisStepCount = 0;

const analyzeStep = tool({
  description: 'Perform one step of data analysis. Returns partial results.',
  parameters: z.object({
    aspect: z.string().describe('What aspect to analyze'),
  }),
  execute: async ({ aspect }) => {
    analysisStepCount++;
    return {
      aspect,
      finding: `Analysis of "${aspect}": trend is positive (step ${analysisStepCount})`,
      complete: analysisStepCount >= 3,
    };
  },
});

const summarize = tool({
  description: 'Summarize all analysis findings into a final report.',
  parameters: z.object({
    findings: z.array(z.string()).describe('List of findings to summarize'),
  }),
  execute: async ({ findings }) => ({
    summary: `Final report based on ${findings.length} findings.`,
    conclusion: 'Overall trend is positive across all analyzed aspects.',
  }),
});

const tools = { analyzeStep, summarize };
const prompt = 'Analyze market trends for AI infrastructure companies. Look at revenue growth, adoption rates, and competitive landscape, then summarize.';
const system = 'You are a market analyst. Analyze each aspect one at a time using the analyzeStep tool, then summarize all findings. Do not analyze more than 3 aspects.';

// ── Path 1: Native with maxSteps ─────────────────────────
async function main() {
  console.log('=== Native Vercel AI SDK (stop conditions) ===');
  analysisStepCount = 0;
  const stepLog: string[] = [];

  const nativeResult = await generateText({
    model,
    system,
    prompt,
    tools,
    maxSteps: 8,
    onStepFinish: (step) => {
      const toolNames = step.toolCalls.map(tc => tc.toolName);
      const reason = step.finishReason;
      stepLog.push(`  Step: finish=${reason}, tools=[${toolNames.join(', ')}]`);
    },
  });

  for (const log of stepLog) console.log(log);
  console.log('Output:', nativeResult.text.slice(0, 300) + (nativeResult.text.length > 300 ? '...' : ''));
  console.log('Total steps:', nativeResult.steps.length);
  console.log('Finish reason:', nativeResult.finishReason);

  // ── Path 1b: With very low maxSteps (forced early stop) ──
  console.log('\n=== Native with maxSteps=2 (forced early stop) ===');
  analysisStepCount = 0;
  const limitedResult = await generateText({
    model,
    system,
    prompt,
    tools,
    maxSteps: 2,
  });
  console.log('Total steps:', limitedResult.steps.length);
  console.log('Finish reason:', limitedResult.finishReason);
  console.log(
    'Tool calls made:',
    limitedResult.steps.flatMap(s => s.toolCalls).map(tc => tc.toolName),
  );

  // ── Path 2: Agentspan passthrough ────────────────────────
  const vercelAgent = {
    id: 'stop_conditions_agent',
    tools,
    generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
      analysisStepCount = 0;
      const result = await generateText({
        model,
        system,
        prompt: opts.prompt,
        tools,
        maxSteps: 8,
        onStepFinish: opts.onStepFinish,
      });
      return {
        text: result.text,
        toolCalls: result.steps.flatMap(s => s.toolCalls),
        toolResults: result.steps.flatMap(s => s.toolResults),
        finishReason: result.finishReason,
        usage: result.usage,
      };
    },
    stream: async function* () { yield { type: 'finish' as const }; },
  };

  console.log('\n=== Agentspan Passthrough ===');
  const runtime = new AgentRuntime();
  try {
    const agentspanResult = await runtime.run(vercelAgent, prompt);
    console.log('Output:', JSON.stringify(agentspanResult.output).slice(0, 300));
    console.log('Status:', agentspanResult.status);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
