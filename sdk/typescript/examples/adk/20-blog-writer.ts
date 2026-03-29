/**
 * Blog Writer -- sequential pipeline for content creation.
 *
 * Demonstrates:
 *   - Sub-agents with outputKey for state management
 *   - Handoff pattern: researcher -> writer -> editor
 *   - Tools for topic research and SEO keyword analysis
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const searchTopic = new FunctionTool({
  name: 'search_topic',
  description: 'Search for information about a topic.',
  parameters: z.object({
    topic: z.string().describe('The topic to research'),
  }),
  execute: async (args: { topic: string }) => {
    const topics: Record<string, { key_points: string[]; sources: string[] }> = {
      ai: {
        key_points: [
          'AI adoption grew 72% in enterprises in 2024',
          'Generative AI is transforming content creation and coding',
          'AI safety and regulation are top policy priorities',
        ],
        sources: ['TechReview', 'AI Journal', 'Industry Report 2024'],
      },
      sustainability: {
        key_points: [
          'Renewable energy hit 30% of global electricity in 2024',
          'Carbon capture technology is scaling rapidly',
          'Green bonds market exceeded $500B',
        ],
        sources: ['GreenTech Weekly', 'Climate Report', 'Energy Journal'],
      },
    };
    for (const [key, data] of Object.entries(topics)) {
      if (args.topic.toLowerCase().includes(key)) {
        return { found: true, ...data };
      }
    }
    return {
      found: true,
      key_points: [`Key insight about ${args.topic}`],
      sources: ['General Research'],
    };
  },
});

const checkSeoKeywords = new FunctionTool({
  name: 'check_seo_keywords',
  description: 'Get SEO keyword suggestions for a topic.',
  parameters: z.object({
    topic: z.string().describe('The topic to get keywords for'),
  }),
  execute: async (args: { topic: string }) => ({
    primary_keyword: args.topic.toLowerCase().replace(/ /g, '-'),
    related_keywords: [
      `${args.topic} trends`,
      `${args.topic} 2025`,
      `best ${args.topic} practices`,
    ],
    search_volume: 'high',
  }),
});

// ── Sub-agents ────────────────────────────────────────────────────

// Research agent gathers information
export const researcher = new LlmAgent({
  name: 'blog_researcher',
  model,
  description: 'Researches topics and gathers key facts.',
  instruction:
    'You are a research assistant. Use the search tool to gather information ' +
    'about the given topic. Present the key findings clearly.',
  tools: [searchTopic, checkSeoKeywords],
  outputKey: 'research_notes',
});

// Writer creates the blog post draft
export const writer = new LlmAgent({
  name: 'blog_writer',
  model,
  description: 'Writes blog post drafts based on research.',
  instruction:
    'You are a blog writer. Based on the research notes provided, ' +
    'write a short blog post (3-4 paragraphs). Include a catchy title. ' +
    'Incorporate SEO keywords naturally.',
  outputKey: 'blog_draft',
});

// Editor polishes the post
export const editor = new LlmAgent({
  name: 'blog_editor',
  model,
  description: 'Edits and polishes blog posts.',
  instruction:
    'You are a blog editor. Review and polish the blog draft. ' +
    'Improve clarity, flow, and engagement. Keep the same length. ' +
    'Output only the final polished blog post.',
});

// ── Coordinator ───────────────────────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'content_coordinator',
  model,
  instruction:
    'You are a content coordinator. First use the researcher to gather information, ' +
    'then the writer to create a draft, and finally the editor to polish it. ' +
    'Present the final blog post to the user.',
  subAgents: [researcher, writer, editor],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(coordinator);
    await runtime.serve(coordinator);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // coordinator,
    // 'Write a blog post about the conductor oss workflow and how its the best workflow engine for the agentic era. ' +
    // 'Make sure to write at-least 5000 word and use markdown to format the content',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('20-blog-writer.ts') || process.argv[1]?.endsWith('20-blog-writer.js')) {
  main().catch(console.error);
}
