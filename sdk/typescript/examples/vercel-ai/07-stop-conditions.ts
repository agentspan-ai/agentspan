/**
 * Vercel AI SDK Tools + Native Agent -- Termination Conditions
 *
 * Demonstrates agentspan's termination condition system on a native Agent
 * with AI SDK tools. Termination conditions control when the agent stops:
 * - MaxMessage: stop after N messages
 * - TextMention: stop when output contains specific text
 * - Composable with .and() / .or()
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  MaxMessage,
  TextMention,
} from '../../src/index.js';

// ── Tool state ───────────────────────────────────────────
let analysisStepCount = 0;

// ── Vercel AI SDK tools ──────────────────────────────────
const analyzeStep = aiTool({
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

const summarize = aiTool({
  description: 'Summarize all analysis findings into a final report.',
  parameters: z.object({
    findings: z.array(z.string()).describe('List of findings to summarize'),
  }),
  execute: async ({ findings }) => ({
    summary: `Final report based on ${findings.length} findings.`,
    conclusion: 'Overall trend is positive across all analyzed aspects.',
  }),
});

// ── Termination: stop on "ANALYSIS COMPLETE" or after 10 messages ──
const termination = new TextMention('ANALYSIS COMPLETE').or(new MaxMessage(10));

// ── Native Agent with AI SDK tools and termination ───────
const agent = new Agent({
  name: 'stop_conditions_agent',
  model: 'openai/gpt-4o-mini',
  instructions:
    'You are a market analyst. Analyze each aspect one at a time using the analyzeStep tool, ' +
    'then summarize all findings. Do not analyze more than 3 aspects. ' +
    'When done, include "ANALYSIS COMPLETE" in your final response.',
  tools: [analyzeStep, summarize],
  termination,
  maxTurns: 8,
});

const prompt =
  'Analyze market trends for AI infrastructure companies. Look at revenue growth, adoption rates, and competitive landscape, then summarize.';

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  analysisStepCount = 0;
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    console.log('Tool calls:', result.toolCalls.length);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
