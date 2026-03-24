/**
 * Web Search Agent -- agent that performs search and summarization with tools.
 *
 * Demonstrates:
 *   - Simulated web search tool returning structured results (mock data)
 *   - Page fetch tool returning mock content
 *   - ChatOpenAI reasoning about search results and summarizing
 *   - Running via AgentRuntime
 *
 * NOTE: This example uses mock search/fetch results for reproducibility.
 * For production, integrate Tavily, SerpAPI, or Brave Search.
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Mock search index (simulates web search API) ─────────

interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

const searchIndex: Record<string, SearchResult[]> = {
  langchain: [
    { title: 'LangChain Documentation', url: 'https://docs.langchain.com', snippet: 'LangChain is a framework for building applications with LLMs. It provides modules for chains, agents, memory, and retrieval.' },
    { title: 'LangChain GitHub', url: 'https://github.com/langchain-ai/langchain', snippet: 'Open-source Python and JavaScript library with 80k+ GitHub stars.' },
  ],
  langgraph: [
    { title: 'LangGraph Docs', url: 'https://langchain-ai.github.io/langgraph/', snippet: 'LangGraph is a library for building stateful multi-actor applications with LLMs, built on top of LangChain.' },
    { title: 'LangGraph Tutorial', url: 'https://blog.langchain.dev/langgraph/', snippet: 'LangGraph introduces graph-based orchestration of LLM workflows with support for cycles, branching, and persistence.' },
  ],
  python: [
    { title: 'Python.org', url: 'https://www.python.org', snippet: 'Python is a versatile, high-level programming language. The latest version is Python 3.13.' },
  ],
  openai: [
    { title: 'OpenAI API', url: 'https://platform.openai.com/docs', snippet: 'The OpenAI API provides access to GPT-4, DALL-E, Whisper, and Embeddings models via REST API.' },
  ],
};

const pageContent: Record<string, string> = {
  'docs.langchain.com': 'LangChain provides components including LLMs, PromptTemplates, Chains, Agents, and Memory. The LCEL allows composing these components with the | operator.',
  'langchain-ai.github.io/langgraph': 'LangGraph is built on top of LangChain and uses a graph-based approach where nodes are Python functions and edges define the flow between them. Supports cycles, persistence, and human-in-the-loop.',
  'python.org': 'Python 3.13 is the latest stable release. Key features include improved error messages and a free-threaded build option.',
  'platform.openai.com': "GPT-4o is OpenAI's most capable and efficient model. The API supports text, images, and function calling.",
};

// ── Tool definitions ─────────────────────────────────────

const webSearchTool = new DynamicStructuredTool({
  name: 'web_search',
  description: 'Search the web for information. Returns a list of search results with titles, URLs, and snippets.',
  schema: z.object({
    query: z.string().describe('The search query'),
  }),
  func: async ({ query }) => {
    const queryLower = query.toLowerCase();
    const results: SearchResult[] = [];
    for (const [keyword, entries] of Object.entries(searchIndex)) {
      if (queryLower.includes(keyword)) results.push(...entries);
    }
    if (results.length === 0) {
      return JSON.stringify([{
        title: `No results for '${query}'`,
        url: `https://search.example.com/?q=${encodeURIComponent(query)}`,
        snippet: `No cached results available for '${query}'.`,
      }]);
    }
    return JSON.stringify(results.slice(0, 3), null, 2);
  },
});

const fetchPageTool = new DynamicStructuredTool({
  name: 'fetch_page',
  description: 'Fetch and summarize the content of a web page given its URL.',
  schema: z.object({
    url: z.string().describe('The URL to fetch'),
  }),
  func: async ({ url }) => {
    for (const [key, content] of Object.entries(pageContent)) {
      if (url.includes(key)) return `Page content from ${url}:\n${content}`;
    }
    return `Page at ${url} returned general information. (Mock result)`;
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [webSearchTool, fetchPageTool];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runSearchAgent(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage(
      'You are a research assistant. Use web_search to find information, then optionally ' +
      'use fetch_page to get more details from specific URLs. Synthesize the results into ' +
      'a clear, well-organized summary with citations.'
    ),
    new HumanMessage(prompt),
  ];

  for (let i = 0; i < 6; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    for (const tc of toolCalls) {
      const tool = toolMap[tc.name];
      if (tool) {
        const result = await (tool as any).invoke(tc.args);
        messages.push(new ToolMessage({ content: String(result), tool_call_id: tc.id! }));
      }
    }
  }

  return 'Agent reached maximum iterations.';
}

// ── Wrap for Agentspan ───────────────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runSearchAgent(input.input);
    return { output };
  },
});

// Add agentspan metadata for extraction
(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langchain',
};

async function main() {
  const userPrompt = 'Search for information about LangGraph and summarize what you find.';

  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agentRunnable, userPrompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
