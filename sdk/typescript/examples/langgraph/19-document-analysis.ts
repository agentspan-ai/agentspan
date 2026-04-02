/**
 * Document Analysis Agent -- createReactAgent with document processing tools.
 *
 * Demonstrates:
 *   - A suite of document analysis tools: read, extract entities, summarize, classify sentiment
 *   - Realistic mock implementations returning structured data
 *   - Chaining multiple tools to produce a comprehensive document report
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Mock document store
// ---------------------------------------------------------------------------
const DOCUMENTS: Record<string, string> = {
  quarterly_report:
    'Q3 2024 Performance Report: Our revenue grew 23% year-over-year to $4.2 billion. ' +
    'CEO Jane Smith announced the acquisition of TechCorp Ltd for $800 million. ' +
    'Product launches in APAC markets exceeded expectations. ' +
    'CFO John Doe highlighted cost-cutting measures saving $120 million annually. ' +
    'Headcount increased by 1,200 employees across North America and Europe.',
  product_review:
    'This smartphone is absolutely fantastic! The camera quality is stunning and the battery ' +
    'lasts two full days. However, the price point is too high for most consumers. ' +
    'Customer service was responsive when I had questions about setup. ' +
    'Overall, a premium device that delivers on its promises, though not for budget shoppers.',
  incident_report:
    'On March 15, 2024, a service outage occurred affecting systems in region US-EAST-1. ' +
    'Root cause: database connection pool exhaustion due to an unoptimized query in v2.3.1. ' +
    'Engineering lead Sarah Chen resolved the issue within 90 minutes. ' +
    'Impact: 3,400 users affected, $45,000 estimated revenue loss. ' +
    'Mitigation: query optimization deployed, connection limits increased.',
};

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const readDocumentTool = new DynamicStructuredTool({
  name: 'read_document',
  description:
    "Load the full text of a document by its ID. " +
    "Available IDs: 'quarterly_report', 'product_review', 'incident_report'.",
  schema: z.object({
    document_id: z.string().describe('The document identifier'),
  }),
  func: async ({ document_id }) => {
    const content = DOCUMENTS[document_id.toLowerCase().replace(/ /g, '_')];
    if (!content) {
      const available = Object.keys(DOCUMENTS).join(', ');
      return `Document '${document_id}' not found. Available: ${available}`;
    }
    return content;
  },
});

const extractEntitiesTool = new DynamicStructuredTool({
  name: 'extract_entities',
  description:
    'Extract named entities (people, organizations, monetary values, dates) from text.',
  schema: z.object({
    text: z.string().describe('The text to extract entities from'),
  }),
  func: async ({ text }) => {
    const entities: Record<string, string[]> = {
      people: [],
      organizations: [],
      monetary: [],
      dates: [],
    };

    // Simple heuristic patterns for mock extraction
    const moneyPattern = /\$[\d,.]+ (?:billion|million|thousand)?/g;
    const datePattern = /\b(?:Q[1-4] \d{4}|\w+ \d{1,2},? \d{4})\b/g;

    if (text.includes('Jane Smith')) entities.people.push('Jane Smith (CEO)');
    if (text.includes('John Doe')) entities.people.push('John Doe (CFO)');
    if (text.includes('Sarah Chen'))
      entities.people.push('Sarah Chen (Engineering Lead)');
    if (text.includes('TechCorp'))
      entities.organizations.push('TechCorp Ltd');

    entities.monetary = (text.match(moneyPattern) ?? []).slice(0, 5);
    entities.dates = (text.match(datePattern) ?? []).slice(0, 5);

    const lines: string[] = [];
    for (const [category, items] of Object.entries(entities)) {
      if (items.length > 0) {
        const label = category.charAt(0).toUpperCase() + category.slice(1);
        lines.push(`${label}: ${items.join(', ')}`);
      }
    }
    return lines.length > 0 ? lines.join('\n') : 'No named entities detected.';
  },
});

const summarizeDocumentTool = new DynamicStructuredTool({
  name: 'summarize_document',
  description: 'Summarize the given text in approximately max_words words.',
  schema: z.object({
    text: z.string().describe('The text to summarize'),
    max_words: z
      .number()
      .optional()
      .describe('Approximate max words in summary (default 50)'),
  }),
  func: async ({ text, max_words }) => {
    const limit = max_words ?? 50;
    const sentences = text
      .split('.')
      .map((s) => s.trim())
      .filter((s) => s.length > 20);
    const selected = sentences.slice(0, 2);
    let summary = selected.join('. ') + '.';
    const words = summary.split(/\s+/);
    if (words.length > limit) {
      summary = words.slice(0, limit).join(' ') + '...';
    }
    return summary;
  },
});

const classifySentimentTool = new DynamicStructuredTool({
  name: 'classify_sentiment',
  description:
    'Classify the overall sentiment of text as positive, negative, neutral, or mixed.',
  schema: z.object({
    text: z.string().describe('The text to classify sentiment of'),
  }),
  func: async ({ text }) => {
    const textLower = text.toLowerCase();
    const positiveWords = [
      'grew',
      'exceeded',
      'fantastic',
      'stunning',
      'resolved',
      'success',
    ];
    const negativeWords = [
      'outage',
      'loss',
      'affected',
      'high price',
      'exhaustion',
    ];

    const posCount = positiveWords.filter((w) => textLower.includes(w)).length;
    const negCount = negativeWords.filter((w) => textLower.includes(w)).length;

    let sentiment: string;
    let confidence: string;
    if (posCount > negCount * 2) {
      sentiment = 'POSITIVE';
      confidence = 'high';
    } else if (negCount > posCount) {
      sentiment = 'NEGATIVE';
      confidence = 'medium';
    } else if (posCount > 0 && negCount > 0) {
      sentiment = 'MIXED';
      confidence = 'medium';
    } else {
      sentiment = 'NEUTRAL';
      confidence = 'low';
    }

    return (
      `Sentiment: ${sentiment}\n` +
      `Confidence: ${confidence}\n` +
      `Positive signals: ${posCount}, Negative signals: ${negCount}`
    );
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const tools = [
  readDocumentTool,
  extractEntitiesTool,
  summarizeDocumentTool,
  classifySentimentTool,
];
const graph = createReactAgent({
  llm,
  tools,
  prompt:
    'You are a professional document analyst. When asked to analyze a document: ' +
    '1) Read it using read_document, ' +
    '2) Extract entities, ' +
    '3) Summarize the key points, ' +
    '4) Classify sentiment. ' +
    'Combine findings into a structured report.',
});

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const PROMPT =
  "Please provide a full analysis of the 'quarterly_report' document.";

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents document_analysis
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('19-document-analysis.ts') || process.argv[1]?.endsWith('19-document-analysis.js')) {
  main().catch(console.error);
}
