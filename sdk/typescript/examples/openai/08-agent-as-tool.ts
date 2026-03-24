// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent -- Manager Pattern with agents-as-tools.
 *
 * Demonstrates:
 *   - Using Agent.asTool() to expose specialist agents as tools
 *   - A manager agent that delegates to specialists via tool calls
 *   - Differs from handoffs: manager retains control and synthesizes results
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, tool, setTracingDisabled } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Specialist tools ────────────────────────────────────────────────

const analyzeSentiment = tool({
  name: 'analyze_sentiment',
  description: 'Analyze the sentiment of text. Returns positive, negative, or neutral.',
  parameters: z.object({ text: z.string().describe('Text to analyze') }),
  execute: async ({ text }) => {
    const positiveWords = new Set(['great', 'love', 'excellent', 'amazing', 'wonderful', 'best']);
    const negativeWords = new Set(['bad', 'terrible', 'hate', 'awful', 'worst', 'horrible']);

    const words = new Set(text.toLowerCase().split(/\s+/));
    let pos = 0;
    let neg = 0;
    for (const w of words) {
      if (positiveWords.has(w)) pos++;
      if (negativeWords.has(w)) neg++;
    }

    if (pos > neg) return `Positive sentiment (score: ${pos}/${pos + neg})`;
    if (neg > pos) return `Negative sentiment (score: ${neg}/${pos + neg})`;
    return 'Neutral sentiment';
  },
});

const extractKeywords = tool({
  name: 'extract_keywords',
  description: 'Extract key topics and keywords from text.',
  parameters: z.object({ text: z.string().describe('Text to extract keywords from') }),
  execute: async ({ text }) => {
    const stopWords = new Set([
      'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at',
      'to', 'for', 'of', 'and', 'or', 'but', 'with', 'this', 'that', 'i',
    ]);
    const words = text.toLowerCase().split(/\s+/);
    const keywords = words
      .map((w) => w.replace(/[.,!?]/g, ''))
      .filter((w) => !stopWords.has(w) && w.length > 3);
    const unique = [...new Set(keywords)].slice(0, 10);
    return `Keywords: ${unique.join(', ')}`;
  },
});

// ── Specialist agents ───────────────────────────────────────────────

const sentimentAgent = new Agent({
  name: 'sentiment_analyzer',
  instructions:
    'You analyze text sentiment. Use the analyze_sentiment tool and provide a brief interpretation.',
  model: 'gpt-4o-mini',
  tools: [analyzeSentiment],
});

const keywordAgent = new Agent({
  name: 'keyword_extractor',
  instructions:
    'You extract keywords from text. Use the extract_keywords tool and categorize the results.',
  model: 'gpt-4o-mini',
  tools: [extractKeywords],
});

// ── Manager agent ───────────────────────────────────────────────────

const manager = new Agent({
  name: 'text_analysis_manager',
  instructions:
    'You are a text analysis manager. When given text to analyze:\n' +
    '1. Use the sentiment analyzer to understand the tone\n' +
    '2. Use the keyword extractor to identify key topics\n' +
    '3. Synthesize the results into a concise summary\n\n' +
    'Always use both tools before providing your summary.',
  model: 'gpt-4o-mini',
  tools: [
    sentimentAgent.asTool({
      toolName: 'sentiment_analyzer',
      toolDescription: 'Analyze the sentiment of text using a specialist agent.',
    }),
    keywordAgent.asTool({
      toolName: 'keyword_extractor',
      toolDescription: 'Extract keywords and topics from text using a specialist agent.',
    }),
  ],
});

const prompt =
  "Analyze this review: 'The new laptop is excellent! The display is amazing " +
  "and the battery life is wonderful. However, the keyboard feels terrible " +
  "and the trackpad is the worst I've used.'";

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(manager, prompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
