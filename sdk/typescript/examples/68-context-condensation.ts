/**
 * 68 - Context Condensation Stress Test — orchestrator + sub-agent, history condenses 3+ times.
 *
 * An orchestrator agent calls a deep_analyst sub-agent once per technology domain.
 * Each sub-agent result lands in the orchestrator's conversation history as a large
 * tool-call output. After roughly 10 calls the accumulated history exceeds the
 * configured context window and the server automatically condenses it.
 *
 * Setup: set agentspan.default-context-window=10000 in server config.
 *
 * Requirements:
 *   - Conductor server with LLM support + agentspan.default-context-window=10000
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, agentTool, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Domain data -------------------------------------------------------------

const DOMAIN_DATA: Record<string, Record<string, unknown>> = {
  'machine learning': {
    market_size: '$158B (2024), projected $529B by 2030',
    cagr: '22.8%',
    top_players: ['Google DeepMind', 'OpenAI', 'Meta AI', 'Microsoft', 'Hugging Face'],
    key_verticals: ['healthcare diagnostics', 'financial fraud detection', 'autonomous systems', 'NLP'],
    recent_breakthroughs: 'Mixture-of-Experts scaling, test-time compute, multimodal foundation models',
    open_challenges: 'interpretability, data efficiency, energy consumption, hallucination',
    regulatory_highlights: 'EU AI Act risk tiers, US EO 14110, China AIGC regulations',
  },
  'large language models': {
    market_size: '$6.4B (2024), projected $36B by 2030',
    cagr: '33.2%',
    top_players: ['OpenAI', 'Anthropic', 'Google', 'Meta', 'Mistral'],
    key_verticals: ['coding assistants', 'enterprise search', 'customer support', 'document generation'],
    recent_breakthroughs: 'long-context (1M+ tokens), reasoning models (o1/o3), tool-use chains',
    open_challenges: 'factual accuracy, context faithfulness, cost per token, alignment at scale',
    regulatory_highlights: 'watermarking requirements, bias audits, disclosure obligations',
  },
  'retrieval-augmented generation': {
    market_size: '$1.2B (2024), projected $11B by 2029',
    cagr: '49%',
    top_players: ['Pinecone', 'Weaviate', 'Cohere', 'LlamaIndex', 'LangChain'],
    key_verticals: ['enterprise knowledge bases', 'legal research', 'medical Q&A', 'technical support'],
    recent_breakthroughs: 'graph RAG, multi-hop retrieval, hybrid BM25+embedding search',
    open_challenges: 'retrieval faithfulness, chunking strategy, latency, stale data',
    regulatory_highlights: 'data provenance tracking, GDPR right-to-erasure in vector stores',
  },
  'computer vision': {
    market_size: '$22B (2024), projected $86B by 2030',
    cagr: '25.1%',
    top_players: ['NVIDIA', 'Intel', 'Qualcomm', 'Google', 'Amazon Rekognition'],
    key_verticals: ['manufacturing QC', 'retail analytics', 'medical imaging', 'security surveillance'],
    recent_breakthroughs: 'vision transformers at scale, video understanding, 3D scene reconstruction',
    open_challenges: 'adversarial robustness, edge deployment, annotation cost, privacy',
    regulatory_highlights: 'facial recognition bans, biometric data laws (BIPA, GDPR Art. 9)',
  },
  'autonomous vehicles': {
    market_size: '$54B (2024), projected $557B by 2035',
    cagr: '28.5%',
    top_players: ['Waymo', 'Tesla', 'Mobileye', 'Cruise', 'Baidu Apollo'],
    key_verticals: ['ride-hailing', 'trucking & logistics', 'last-mile delivery', 'mining'],
    recent_breakthroughs: 'end-to-end neural driving, HD map-free navigation, V2X communication',
    open_challenges: 'edge-case handling, liability frameworks, sensor cost, public trust',
    regulatory_highlights: 'NHTSA AV framework, EU regulation 2022/2065, state-level AV laws',
  },
  'AI safety and alignment': {
    market_size: '$500M in dedicated research funding (2024)',
    cagr: 'Rapidly growing -- 3x YoY in funding',
    top_players: ['Anthropic', 'DeepMind Safety', 'ARC Evals', 'Redwood Research', 'Center for AI Safety'],
    key_verticals: ['red-teaming', 'constitutional AI', 'interpretability', 'scalable oversight'],
    recent_breakthroughs: 'sparse autoencoders for feature circuits, debate as alignment method',
    open_challenges: 'specification gaming, power-seeking behaviour, deceptive alignment',
    regulatory_highlights: 'EU AI Act Art. 9, US AI Safety Institute, GPAI Code of Practice',
  },
  'diffusion models': {
    market_size: '$3.2B (2024), projected $18B by 2030',
    cagr: '33%',
    top_players: ['Stability AI', 'Midjourney', 'OpenAI (DALL-E)', 'Adobe Firefly', 'Runway'],
    key_verticals: ['creative content', 'drug design', 'video synthesis', '3D asset generation'],
    recent_breakthroughs: 'video diffusion (Sora, Runway), consistency models, latent diffusion',
    open_challenges: 'copyright attribution, deepfake misuse, training data consent, compute cost',
    regulatory_highlights: 'C2PA content provenance standard, EU synthetic media disclosure rules',
  },
  'reinforcement learning': {
    market_size: '$2.1B (2024), projected $12B by 2030',
    cagr: '29%',
    top_players: ['Google DeepMind', 'OpenAI', 'Microsoft', 'Cohere (RLHF)', 'Hugging Face TRL'],
    key_verticals: ['RLHF for LLMs', 'game AI', 'robotics control', 'financial trading'],
    recent_breakthroughs: 'GRPO for reasoning, RLVR (verifiable rewards), self-play at scale',
    open_challenges: 'reward hacking, sample efficiency, sim-to-real transfer, sparse rewards',
    regulatory_highlights: 'gaming regulations (addictive mechanics), algorithmic trading oversight',
  },
};

const DEFAULT_DOMAIN_DATA: Record<string, unknown> = {
  market_size: 'Data not available',
  cagr: 'Growing rapidly',
  top_players: ['Various vendors'],
  key_verticals: ['Enterprise', 'Consumer', 'Research'],
  recent_breakthroughs: 'Active research and development',
  open_challenges: 'Scalability, cost, adoption',
  regulatory_highlights: 'Evolving global frameworks',
};

// -- Tool used by the sub-agent ----------------------------------------------

const fetchDomainData = tool(
  async (args: { domain: string }) => {
    const key = args.domain.toLowerCase().trim();
    if (DOMAIN_DATA[key]) return DOMAIN_DATA[key];
    for (const [k, v] of Object.entries(DOMAIN_DATA)) {
      if (k.includes(key) || key.includes(k)) return v;
    }
    return { ...DEFAULT_DOMAIN_DATA, domain: args.domain };
  },
  {
    name: 'fetch_domain_data',
    description:
      'Fetch market data, statistics, and key facts for a technology domain.',
    inputSchema: z.object({
      domain: z.string().describe('The technology domain to research'),
    }),
  },
);

// -- Sub-agent: calls fetchDomainData and writes analysis --------------------

export const deepAnalyst = new Agent({
  name: 'deep_analyst_68',
  model: llmModel,
  tools: [fetchDomainData],
  instructions:
    'You are an expert technology analyst at a top-tier research firm. ' +
    'When asked to analyse a domain:\n' +
    '1. First call fetch_domain_data to retrieve the raw facts.\n' +
    '2. Then write a COMPREHENSIVE, DETAILED analysis structured as follows:\n\n' +
    '## Executive Summary\n' +
    '## Market Overview\n' +
    '## Technology Landscape\n' +
    '## Key Players & Competitive Dynamics\n' +
    '## Use Cases & Industry Applications\n' +
    '## Recent Breakthroughs & Innovation\n' +
    '## Challenges & Barriers to Adoption\n' +
    '## Regulatory & Policy Environment\n' +
    '## 5-Year Strategic Outlook\n\n' +
    'Be specific, detailed, and rigorous. Minimum 500 words.',
});

// -- Orchestrator ------------------------------------------------------------

const DOMAINS = Object.keys(DOMAIN_DATA);

export const orchestrator = new Agent({
  name: 'research_orchestrator_68',
  model: llmModel,
  tools: [agentTool(deepAnalyst)],
  instructions:
    'You are a research director compiling a technology landscape report. ' +
    'Process ONE domain per turn -- call deep_analyst for exactly ONE domain, ' +
    'wait for the result, then call it for the next domain. ' +
    'Never call deep_analyst for more than one domain at a time. ' +
    'Keep a running count of which domains you have completed. ' +
    'After ALL domains are done, write a 5-bullet cross-domain executive ' +
    'summary highlighting the most important trends observed across all reports.',
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(orchestrator);
    await runtime.serve(orchestrator);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // orchestrator,
    // 'Produce comprehensive analyses for each of the following technology domains ' +
    // 'by calling deep_analyst ONCE PER DOMAIN, one domain at a time (not in parallel). ' +
    // `Complete all ${DOMAINS.length} domains, then summarise cross-domain trends. ` +
    // `Domains: ${DOMAINS.join(', ')}.`,
    // );
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('68-context-condensation.ts') || process.argv[1]?.endsWith('68-context-condensation.js')) {
  main().catch(console.error);
}
