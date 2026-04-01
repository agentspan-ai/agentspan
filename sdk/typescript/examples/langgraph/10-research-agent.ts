/**
 * Research Agent -- createReactAgent with search, summarize, and cite_source tools.
 *
 * Demonstrates:
 *   - Combining search, summarization, and citation tools in one agent
 *   - Mock tool implementations returning realistic research-style data
 *   - Building a multi-step research workflow via tool chaining
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Mock research database
// ---------------------------------------------------------------------------
const SEARCH_DB: Record<string, string[]> = {
  'climate change': [
    'Global temperatures have risen ~1.1C since pre-industrial times (IPCC, 2023).',
    'Sea levels are rising at 3.7 mm/year due to thermal expansion and ice melt.',
    'Extreme weather events have increased in frequency and intensity since 1980.',
  ],
  'artificial intelligence': [
    'Large language models (LLMs) have achieved human-level performance on many benchmarks.',
    'The global AI market is projected to reach $1.8 trillion by 2030.',
    'AI ethics and alignment remain active research challenges.',
  ],
  'renewable energy': [
    'Solar PV costs have dropped 89% in the past decade.',
    'Wind power capacity exceeded 900 GW globally in 2023.',
    'Battery storage is the key bottleneck for 100% renewable grids.',
  ],
};

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const searchTool = new DynamicStructuredTool({
  name: 'search',
  description: 'Search for information on a topic. Returns relevant findings.',
  schema: z.object({
    query: z.string().describe('The search query'),
  }),
  func: async ({ query }) => {
    const queryLower = query.toLowerCase();
    for (const [key, results] of Object.entries(SEARCH_DB)) {
      if (queryLower.includes(key)) {
        return results.map((r) => `- ${r}`).join('\n');
      }
    }
    return `No specific results found for '${query}'. Try a broader search term.`;
  },
});

const summarizeTool = new DynamicStructuredTool({
  name: 'summarize',
  description: 'Summarize a block of text into a concise form.',
  schema: z.object({
    text: z.string().describe('The text to summarize'),
    max_sentences: z.number().optional().describe('Maximum sentences in summary (default 3)'),
  }),
  func: async ({ text, max_sentences }) => {
    const limit = max_sentences ?? 3;
    const sentences = text
      .replace(/\n/g, '. ')
      .split('. ')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const selected = sentences.slice(0, limit);
    const result = selected.join('. ');
    return result.endsWith('.') ? result : result + '.';
  },
});

const citeSourceTool = new DynamicStructuredTool({
  name: 'cite_source',
  description: 'Generate an academic citation for a claim.',
  schema: z.object({
    claim: z.string().describe('The claim to cite'),
    source_type: z
      .enum(['academic', 'news', 'report'])
      .optional()
      .describe('Type of source (default: academic)'),
  }),
  func: async ({ claim, source_type }) => {
    const citations: Record<string, string> = {
      academic:
        'Smith, J., & Doe, A. (2024). Research findings on the topic. Journal of Science, 12(3), 45-67.',
      news: 'Reuters. (2024, January 15). New developments in research. Reuters.com.',
      report: 'World Economic Forum. (2024). Global Report 2024. WEF Publications.',
    };
    const st = source_type ?? 'academic';
    const source = citations[st] ?? citations['academic'];
    return `Claim: '${claim.slice(0, 80)}...'\nCitation: ${source}`;
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({
  llm,
  tools: [searchTool, summarizeTool, citeSourceTool],
});

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [searchTool, summarizeTool, citeSourceTool],
  framework: 'langgraph',
};

const PROMPT =
  'What are the latest developments in climate change research? Please search, summarize, and include citations.';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('10-research-agent.ts') || process.argv[1]?.endsWith('10-research-agent.js')) {
  main().catch(console.error);
}
