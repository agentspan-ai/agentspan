// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent -- Multi-Model Handoff with different LLMs.
 *
 * Demonstrates:
 *   - Different agents using different models
 *   - Handoffs between agents with different capabilities
 *   - Model override for cost/performance optimization
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, tool, setTracingDisabled } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Tools ───────────────────────────────────────────────────────────

const searchDocs = tool({
  name: 'search_docs',
  description: 'Search the documentation for relevant information.',
  parameters: z.object({ query: z.string().describe('Search query') }),
  execute: async ({ query }) => {
    const docs: Record<string, string> = {
      authentication: 'Use OAuth 2.0 with JWT tokens. See /auth/login endpoint.',
      'rate limiting': '100 requests/minute per API key. 429 status on exceeded.',
      pagination: 'Use cursor-based pagination with ?cursor=xxx&limit=50.',
      webhooks: 'POST to /webhooks/register with event types and callback URL.',
    };
    for (const [key, value] of Object.entries(docs)) {
      if (query.toLowerCase().includes(key)) return value;
    }
    return 'No documentation found. Try rephrasing your query.';
  },
});

const generateCodeSample = tool({
  name: 'generate_code_sample',
  description: 'Generate a code sample for a given topic.',
  parameters: z.object({
    language: z.string().describe('Programming language'),
    topic: z.string().describe('Topic for the code sample'),
  }),
  execute: async ({ language, topic }) => {
    const samples: Record<string, string> = {
      'python:authentication': [
        "import requests",
        "resp = requests.post('/auth/login', json={'key': 'API_KEY'})",
        "token = resp.json()['token']",
      ].join('\n'),
      'javascript:authentication': [
        "const resp = await fetch('/auth/login', {",
        "  method: 'POST',",
        "  body: JSON.stringify({ key: 'API_KEY' })",
        '});',
        'const { token } = await resp.json();',
      ].join('\n'),
    };
    const key = `${language.toLowerCase()}:${topic.toLowerCase()}`;
    return samples[key] ?? `// Sample for ${topic} in ${language}\n// (template not available)`;
  },
});

// ── Fast, cheap model for initial triage ────────────────────────────

export const triage = new Agent({
  name: 'triage',
  instructions:
    'You are a documentation triage agent. Determine what the user needs ' +
    'and hand off to the appropriate specialist:\n' +
    '- For documentation lookups -> doc_specialist\n' +
    '- For code examples -> code_specialist\n' +
    'Keep your response to one sentence before handing off.',
  model: 'gpt-4o-mini',
  modelSettings: { temperature: 0.1 },
  handoffs: [], // populated below
});

// ── More capable model for doc lookups ──────────────────────────────

export const docSpecialist = new Agent({
  name: 'doc_specialist',
  instructions:
    'You are a documentation specialist. Search the docs and provide ' +
    'clear, well-structured answers. Include relevant links and examples.',
  model: 'gpt-4o',
  tools: [searchDocs],
  modelSettings: { temperature: 0.2, maxTokens: 500 },
});

// ── Code-focused model for code generation ──────────────────────────

export const codeSpecialist = new Agent({
  name: 'code_specialist',
  instructions:
    'You are a code example specialist. Generate clean, well-commented ' +
    'code samples. Always specify the language and include error handling.',
  model: 'gpt-4o',
  tools: [generateCodeSample],
  modelSettings: { temperature: 0.3, maxTokens: 800 },
});

// Wire up handoffs
triage.handoffs = [docSpecialist, codeSpecialist];

const prompt = 'I need a Python code example for authenticating with the API.';

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(triage);
    await runtime.serve(triage);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(triage, prompt);
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('10-multi-model.ts') || process.argv[1]?.endsWith('10-multi-model.js')) {
  main().catch(console.error);
}
