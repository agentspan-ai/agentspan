/**
 * 38 - Tech Trend Analyzer
 *
 * Multi-agent research + analysis + PDF pipeline.
 * Compares two programming languages using real data from:
 *   - HackerNews (community discussion, via Algolia search API)
 *   - PyPI Stats (Python package downloads)
 *   - NPM (JavaScript ecosystem downloads)
 *   - Wikipedia (background / ecosystem context)
 *
 * Architecture:
 *   researcher >> analyst >> pdfGenerator  (sequential pipeline)
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, pdfTool, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Researcher tools (HackerNews + Wikipedia) --------------------------------

const searchHackernews = tool(
  async (args: { query: string; maxResults?: number }) => {
    const max = Math.max(1, Math.min(args.maxResults ?? 8, 20));
    const url =
      `https://hn.algolia.com/api/v1/search` +
      `?query=${encodeURIComponent(args.query)}` +
      `&tags=story&hitsPerPage=${max}`;
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(10000) });
      const data = (await resp.json()) as Record<string, unknown>;
      const hits = (data.hits ?? []) as Record<string, unknown>[];
      const stories = hits.map((h) => ({
        id: String(h.objectID ?? ''),
        title: String(h.title ?? ''),
        points: (h.points as number) ?? 0,
        num_comments: (h.num_comments as number) ?? 0,
        author: String(h.author ?? ''),
        created_at: String(h.created_at ?? '').slice(0, 10),
        story_url: String(h.url ?? ''),
      }));
      return { query: args.query, total_found: data.nbHits ?? 0, stories };
    } catch (exc) {
      return { query: args.query, error: String(exc), stories: [] };
    }
  },
  {
    name: 'search_hackernews',
    description:
      'Search HackerNews for stories about a technology topic. ' +
      'Returns recent stories with title, points, comment count, author, and story ID.',
    inputSchema: z.object({
      query: z.string().describe('Search query'),
      maxResults: z.number().optional().describe('Max results (1-20, default 8)'),
    }),
  },
);

const getHnStoryComments = tool(
  async (args: { storyId: string }) => {
    const url = `https://hn.algolia.com/api/v1/items/${args.storyId}`;
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(10000) });
      const data = (await resp.json()) as Record<string, unknown>;
      const children = ((data.children ?? []) as Record<string, unknown>[]).slice(0, 8);
      const comments = children
        .map((child) => {
          const raw = String(child.text ?? '');
          const clean = raw.replace(/<[^>]+>/g, ' ').trim().replace(/\s+/g, ' ').slice(0, 400);
          return clean ? { author: String(child.author ?? ''), text: clean } : null;
        })
        .filter(Boolean);
      return {
        story_id: args.storyId,
        title: String(data.title ?? ''),
        points: (data.points as number) ?? 0,
        comment_count: ((data.children ?? []) as unknown[]).length,
        top_comments: comments,
      };
    } catch (exc) {
      return { story_id: args.storyId, error: String(exc), top_comments: [] };
    }
  },
  {
    name: 'get_hn_story_comments',
    description:
      'Fetch the top comments for a HackerNews story by its numeric ID. ' +
      'Returns the story title, score, and up to 8 top-level comment excerpts.',
    inputSchema: z.object({
      storyId: z.string().describe('HN story ID'),
    }),
  },
);

const getWikipediaSummary = tool(
  async (args: { topic: string }) => {
    const encoded = encodeURIComponent(args.topic.replace(/ /g, '_'));
    const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encoded}`;
    try {
      const resp = await fetch(url, {
        headers: { 'User-Agent': 'TechTrendAnalyzer/1.0' },
        signal: AbortSignal.timeout(10000),
      });
      const data = (await resp.json()) as Record<string, unknown>;
      return {
        topic: args.topic,
        title: String(data.title ?? ''),
        description: String(data.description ?? ''),
        extract: String(data.extract ?? '').slice(0, 800),
      };
    } catch (exc) {
      return { topic: args.topic, error: String(exc), extract: '' };
    }
  },
  {
    name: 'get_wikipedia_summary',
    description:
      'Fetch the Wikipedia introduction paragraph for a technology or topic. ' +
      'Returns the page title, a short description, and the first ~800 chars of the extract.',
    inputSchema: z.object({
      topic: z.string().describe('The topic to look up'),
    }),
  },
);

// -- Analyst tools (package registries + math) --------------------------------

const fetchPypiDownloads = tool(
  async (args: { package: string }) => {
    const url = `https://pypistats.org/api/packages/${encodeURIComponent(args.package)}/recent`;
    try {
      const resp = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; research-bot/1.0)' },
        signal: AbortSignal.timeout(10000),
      });
      const data = (await resp.json()) as Record<string, unknown>;
      const row = (data.data ?? {}) as Record<string, number>;
      return {
        package: args.package,
        last_day: row.last_day ?? 0,
        last_week: row.last_week ?? 0,
        last_month: row.last_month ?? 0,
      };
    } catch (exc) {
      return { package: args.package, error: String(exc) };
    }
  },
  {
    name: 'fetch_pypi_downloads',
    description:
      'Fetch recent PyPI download statistics for a Python package. ' +
      'Returns last-day, last-week, and last-month download counts.',
    inputSchema: z.object({
      package: z.string().describe('PyPI package name'),
    }),
  },
);

const fetchNpmDownloads = tool(
  async (args: { package: string }) => {
    const encoded = encodeURIComponent(args.package);
    const url = `https://api.npmjs.org/downloads/point/last-month/${encoded}`;
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(10000) });
      const data = (await resp.json()) as Record<string, unknown>;
      return {
        package: args.package,
        downloads_last_month: (data.downloads as number) ?? 0,
        start: String(data.start ?? ''),
        end: String(data.end ?? ''),
      };
    } catch (exc) {
      return { package: args.package, error: String(exc) };
    }
  },
  {
    name: 'fetch_npm_downloads',
    description:
      'Fetch last-month download count for an npm package. ' +
      'Use for JavaScript/TypeScript ecosystem packages.',
    inputSchema: z.object({
      package: z.string().describe('npm package name'),
    }),
  },
);

const compareNumbers = tool(
  async (args: {
    labelA: string;
    valueA: number;
    labelB: string;
    valueB: number;
    metric: string;
  }) => {
    let ratio: number;
    let pctDiff: number;

    if (args.valueB === 0) {
      ratio = args.valueA > 0 ? Infinity : 1.0;
      pctDiff = 100.0;
    } else {
      ratio = Math.round((args.valueA / args.valueB) * 1000) / 1000;
      pctDiff =
        Math.round((Math.abs(args.valueA - args.valueB) / args.valueB) * 1000) / 10;
    }

    const winner = args.valueA >= args.valueB ? args.labelA : args.labelB;
    return {
      metric: args.metric,
      [args.labelA]: args.valueA,
      [args.labelB]: args.valueB,
      ratio: `${args.labelA}/${args.labelB} = ${ratio}`,
      pct_difference: `${pctDiff}%`,
      winner,
    };
  },
  {
    name: 'compare_numbers',
    description:
      'Compute ratio and percentage difference between two numeric values. ' +
      'Useful for comparing HN story counts, download figures, etc.',
    inputSchema: z.object({
      labelA: z.string().describe('Label for value A'),
      valueA: z.number().describe('Numeric value A'),
      labelB: z.string().describe('Label for value B'),
      valueB: z.number().describe('Numeric value B'),
      metric: z.string().describe('Name of the metric being compared'),
    }),
  },
);

// -- Agent definitions --------------------------------------------------------

export const researcher = new Agent({
  name: 'hn_researcher',
  model: llmModel,
  tools: [searchHackernews, getHnStoryComments, getWikipediaSummary],
  maxTokens: 4000,
  instructions:
    'You are a technology research assistant. You MUST call tools to gather real data. ' +
    'Do NOT describe what you are going to do -- just call the tools immediately.\n\n' +
    'REQUIRED STEPS (call tools in this exact order):\n' +
    "1. Call search_hackernews(query='Python programming language', maxResults=8)\n" +
    "2. Call search_hackernews(query='Rust programming language', maxResults=8)\n" +
    '3. From the Python results, call get_hn_story_comments on the story with the most comments\n' +
    '4. From the Rust results, call get_hn_story_comments on the story with the most comments\n' +
    "5. Call get_wikipedia_summary(topic='Python (programming language)')\n" +
    "6. Call get_wikipedia_summary(topic='Rust (programming language)')\n\n" +
    'After ALL 6 tool calls are complete, write a structured report with REAL data:\n\n' +
    'RESEARCH DATA: Python\n' +
    '- HN stories found: [actual number from tool result]\n' +
    '- Stories: [list each story title | points | num_comments]\n' +
    '- Top discussion (story title): [actual comment excerpts]\n' +
    '- Wikipedia: [actual description and extract]\n\n' +
    'RESEARCH DATA: Rust\n' +
    '- HN stories found: [actual number from tool result]\n' +
    '- Stories: [list each story title | points | num_comments]\n' +
    '- Top discussion (story title): [actual comment excerpts]\n' +
    '- Wikipedia: [actual description and extract]\n\n' +
    'Include REAL numbers and titles -- no placeholders.',
});

export const analyst = new Agent({
  name: 'hn_analyst',
  model: llmModel,
  tools: [fetchPypiDownloads, fetchNpmDownloads, compareNumbers],
  maxTokens: 4000,
  instructions:
    'You are a technology trend analyst. You will receive real research data about Python and ' +
    'Rust gathered from HackerNews and Wikipedia. You MUST call tools -- do not describe what ' +
    'you will do, just do it.\n\n' +
    'REQUIRED STEPS:\n' +
    "1. Call fetch_pypi_downloads(package='pip') -- Python ecosystem proxy\n" +
    "2. Call fetch_pypi_downloads(package='maturin') -- Rust/Python interop proxy\n" +
    "3. Call fetch_npm_downloads(package='wasm-pack') -- Rust WebAssembly proxy\n" +
    '4. Count the Python stories and compute average points/comments from the research data. ' +
    "   Then call compare_numbers(labelA='Python', valueA=<avg_points>, " +
    "   labelB='Rust', valueB=<avg_points>, metric='avg_points_per_story')\n" +
    '5. Call compare_numbers for avg_comments_per_story similarly\n\n' +
    'After ALL tool calls, write a final markdown report:\n\n' +
    '# Tech Trend Analysis: Python vs Rust\n\n' +
    '## Executive Summary\n' +
    '(2-3 sentence verdict using actual data)\n\n' +
    '## Head-to-Head: HackerNews Engagement\n' +
    '(table with real numbers: stories found, avg points, avg comments)\n\n' +
    '## Ecosystem Adoption (Package Downloads)\n' +
    '(pip, maturin, wasm-pack download counts and what they mean)\n\n' +
    '## Top Stories on HackerNews\n' +
    '(top 3 for each with real titles, points, comments)\n\n' +
    '## Developer Sentiment\n' +
    '(key themes from real comment excerpts)\n\n' +
    '## Verdict\n' +
    '(data-driven conclusion)',
});

// -- PDF generator agent ------------------------------------------------------

export const pdfGenerator = new Agent({
  name: 'pdf_report_generator',
  model: llmModel,
  tools: [pdfTool()],
  maxTokens: 4000,
  instructions:
    "You receive a markdown report. Your ONLY job is to call the generate_pdf " +
    "tool with the full markdown content to produce a PDF document. " +
    "Pass the entire report as the 'markdown' parameter. " +
    "Do not modify or summarize the content -- pass it through as-is.",
});

// -- Sequential pipeline: researcher feeds analyst, analyst feeds PDF ----------

const pipeline = researcher.pipe(analyst).pipe(pdfGenerator);

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('Starting Tech Trend Analyzer: Python vs Rust');
    console.log('='.repeat(60));
    const result = await runtime.run(
    pipeline,
    'Compare Python and Rust: which has stronger developer mindshare and ' +
    'ecosystem momentum right now? Use real HackerNews data and package ' +
    'download statistics to support your analysis.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(pipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents hn_researcher
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(pipeline);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('38-tech-trends.ts') || process.argv[1]?.endsWith('38-tech-trends.js')) {
  main().catch(console.error);
}
