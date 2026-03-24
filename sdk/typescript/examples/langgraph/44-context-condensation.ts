/**
 * Context Condensation Stress Test -- orchestrator + sub-agents, history condenses 3+ times.
 *
 * An orchestrator agent calls a deep_analyst sub-agent once per technology domain.
 * The sub-agent fetches structured domain facts and writes a comprehensive analysis.
 * Each result lands in the orchestrator's conversation history as a large tool-call
 * output. After roughly 10 calls the accumulated history exceeds the configured
 * context window and the Conductor server automatically condenses it.
 *
 * Architecture:
 *   orchestrator (create_agent)
 *     -> deep_analyst (create_agent, SUB_WORKFLOW) x 25 topics
 *          -> fetch_domain_data(domain) -- structured facts/stats
 *
 * In production you would use:
 *   import { createReactAgent } from '@langchain/langgraph/prebuilt';
 *   const graph = createReactAgent({ llm, tools: [deep_analyst] });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Domain data
// ---------------------------------------------------------------------------
const DOMAIN_DATA: Record<string, Record<string, unknown>> = {
  'machine learning': {
    market_size: '$158B (2024), projected $529B by 2030', cagr: '22.8%',
    top_players: ['Google DeepMind', 'OpenAI', 'Meta AI', 'Microsoft', 'Hugging Face'],
    key_verticals: ['healthcare diagnostics', 'financial fraud detection', 'autonomous systems', 'NLP'],
    recent_breakthroughs: 'Mixture-of-Experts scaling, test-time compute, multimodal foundation models',
  },
  'large language models': {
    market_size: '$6.4B (2024), projected $36B by 2030', cagr: '33.2%',
    top_players: ['OpenAI', 'Anthropic', 'Google', 'Meta', 'Mistral'],
    key_verticals: ['coding assistants', 'enterprise search', 'customer support', 'document generation'],
    recent_breakthroughs: 'long-context (1M+ tokens), reasoning models (o1/o3), tool-use chains',
  },
  'retrieval-augmented generation': {
    market_size: '$1.2B (2024), projected $11B by 2029', cagr: '49%',
    top_players: ['Pinecone', 'Weaviate', 'Cohere', 'LlamaIndex', 'LangChain'],
    key_verticals: ['enterprise knowledge bases', 'legal research', 'medical Q&A', 'technical support'],
    recent_breakthroughs: 'graph RAG, multi-hop retrieval, hybrid BM25+embedding search',
  },
  'computer vision': {
    market_size: '$22B (2024), projected $86B by 2030', cagr: '25.1%',
    top_players: ['NVIDIA', 'Intel', 'Qualcomm', 'Google', 'Amazon Rekognition'],
    key_verticals: ['manufacturing QC', 'retail analytics', 'medical imaging', 'security surveillance'],
    recent_breakthroughs: 'vision transformers at scale, video understanding, 3D scene reconstruction',
  },
  'autonomous vehicles': {
    market_size: '$54B (2024), projected $557B by 2035', cagr: '28.5%',
    top_players: ['Waymo', 'Tesla', 'Mobileye', 'Cruise', 'Baidu Apollo'],
    key_verticals: ['ride-hailing', 'trucking & logistics', 'last-mile delivery', 'mining'],
    recent_breakthroughs: 'end-to-end neural driving, HD map-free navigation, V2X communication',
  },
  'AI in drug discovery': {
    market_size: '$1.5B (2024), projected $9.8B by 2030', cagr: '36%',
    top_players: ['Schrodinger', 'Recursion', 'Insilico Medicine', 'AbSci', 'Isomorphic Labs'],
    key_verticals: ['target identification', 'molecular generation', 'clinical trial design'],
    recent_breakthroughs: 'AlphaFold 3 protein interactions, generative chemistry, digital twins',
  },
  'federated learning': {
    market_size: '$180M (2024), projected $2.8B by 2030', cagr: '55%',
    top_players: ['Google (FL framework)', 'Apple', 'NVIDIA FLARE', 'PySyft (OpenMined)', 'IBM'],
    key_verticals: ['mobile keyboard prediction', 'healthcare (NHS FL consortium)', 'financial fraud'],
    recent_breakthroughs: 'secure aggregation at scale, differential privacy budgets, asynchronous FL',
  },
  'graph neural networks': {
    market_size: '$290M (2024), projected $2.1B by 2029', cagr: '48%',
    top_players: ['Google (GraphCast)', 'Meta (PyG)', 'Amazon', 'Snap', 'AstraZeneca'],
    key_verticals: ['drug-protein interaction', 'fraud graph detection', 'recommendation systems'],
    recent_breakthroughs: 'scalable GNNs (GraphSAGE variants), temporal GNNs, physics-informed GNNs',
  },
  'diffusion models': {
    market_size: '$3.2B (2024), projected $18B by 2030', cagr: '33%',
    top_players: ['Stability AI', 'Midjourney', 'OpenAI (DALL-E)', 'Adobe Firefly', 'Runway'],
    key_verticals: ['creative content', 'drug design', 'video synthesis', '3D asset generation'],
    recent_breakthroughs: 'video diffusion (Sora, Runway), consistency models, latent diffusion',
  },
  'reinforcement learning': {
    market_size: '$2.1B (2024), projected $12B by 2030', cagr: '29%',
    top_players: ['Google DeepMind', 'OpenAI', 'Microsoft', 'Cohere (RLHF)', 'Hugging Face TRL'],
    key_verticals: ['RLHF for LLMs', 'game AI', 'robotics control', 'financial trading'],
    recent_breakthroughs: 'GRPO for reasoning, RLVR (verifiable rewards), self-play at scale',
  },
  'AI safety and alignment': {
    market_size: '$500M in dedicated research funding (2024)', cagr: '3x YoY',
    top_players: ['Anthropic', 'DeepMind Safety', 'ARC Evals', 'Redwood Research', 'CAIS'],
    key_verticals: ['red-teaming', 'constitutional AI', 'interpretability', 'scalable oversight'],
    recent_breakthroughs: 'sparse autoencoders for feature circuits, debate as alignment',
  },
  'natural language processing': {
    market_size: '$29B (2024), projected $112B by 2030', cagr: '25%',
    top_players: ['Google', 'Meta', 'Hugging Face', 'Cohere', 'AI21 Labs'],
    key_verticals: ['machine translation', 'sentiment analysis', 'information extraction'],
    recent_breakthroughs: 'instruction tuning, chain-of-thought prompting, mixture of experts',
  },
  'multimodal AI': {
    market_size: '$4.5B (2024), projected $35B by 2030', cagr: '41%',
    top_players: ['Google Gemini', 'OpenAI GPT-4o', 'Anthropic Claude', 'Meta LLaMA-Vision'],
    key_verticals: ['visual Q&A', 'document intelligence', 'video analysis', 'audio understanding'],
    recent_breakthroughs: 'native audio/video tokens, any-to-any models, real-time multimodal agents',
  },
  'robotics and embodied AI': {
    market_size: '$23B (2024), projected $87B by 2030', cagr: '25%',
    top_players: ['Boston Dynamics', 'Figure AI', '1X Technologies', 'Agility Robotics'],
    key_verticals: ['warehouse automation', 'surgical robots', 'agricultural robots'],
    recent_breakthroughs: 'vision-language-action models (RT-2), dexterous manipulation',
  },
  'knowledge graphs': {
    market_size: '$1.1B (2024), projected $5.9B by 2030', cagr: '29%',
    top_players: ['Neo4j', 'Amazon Neptune', 'Google Knowledge Graph', 'Ontotext'],
    key_verticals: ['enterprise search', 'drug-disease networks', 'fraud detection'],
    recent_breakthroughs: 'LLM + KG hybrid (GraphRAG), temporal knowledge graphs',
  },
  'AI in climate modelling': {
    market_size: '$800M (2024), growing rapidly', cagr: '38%',
    top_players: ['Google DeepMind (GraphCast)', 'Huawei Pangu-Weather', 'ECMWF', 'NVIDIA Earth-2'],
    key_verticals: ['weather forecasting', 'climate simulation', 'carbon capture optimisation'],
    recent_breakthroughs: '10-day weather at 0.25 degree resolution in under 1 minute',
  },
  'AI ethics and governance': {
    market_size: '$400M (2024) in tooling/audit services', cagr: '45%',
    top_players: ['IBM OpenScale', 'Fiddler AI', 'Arthur AI', 'Credo AI', 'Holistic AI'],
    key_verticals: ['model auditing', 'bias detection', 'explainability tooling'],
    recent_breakthroughs: 'counterfactual fairness frameworks, differential privacy audits',
  },
  'foundation models': {
    market_size: '$13B (2024), projected $89B by 2030', cagr: '37%',
    top_players: ['OpenAI', 'Anthropic', 'Google', 'Meta', 'Mistral', 'Cohere'],
    key_verticals: ['code generation', 'scientific research', 'creative content'],
    recent_breakthroughs: '1M+ context windows, MoE at trillion parameters, RLVR reasoning chains',
  },
  'AI in financial forecasting': {
    market_size: '$12B (2024), projected $46B by 2030', cagr: '25%',
    top_players: ['Bloomberg AI', 'Two Sigma', 'Renaissance Technologies', 'JPMorgan AI'],
    key_verticals: ['algorithmic trading', 'credit scoring', 'fraud detection', 'risk management'],
    recent_breakthroughs: 'LLMs for earnings call analysis, graph ML for systemic risk',
  },
  'AI in education': {
    market_size: '$5.8B (2024), projected $25B by 2030', cagr: '28%',
    top_players: ['Khan Academy (Khanmigo)', 'Duolingo', 'Chegg', 'Carnegie Learning'],
    key_verticals: ['intelligent tutoring', 'automated essay grading', 'personalised learning'],
    recent_breakthroughs: 'Socratic dialogue via LLMs, knowledge tracing with transformers',
  },
  'neural architecture search': {
    market_size: '$420M (2024), projected $2.5B by 2030', cagr: '35%',
    top_players: ['Google (AutoML)', 'Microsoft (Azure NNI)', 'Huawei (DARTS)', 'MIT HAN Lab'],
    key_verticals: ['mobile edge deployment', 'chip-aware design', 'NLP efficiency'],
    recent_breakthroughs: 'once-for-all networks, zero-shot NAS proxy metrics',
  },
  'causal inference with AI': {
    market_size: '$650M (2024), growing 42% annually', cagr: '42%',
    top_players: ['Microsoft Research (DoWhy)', 'Amazon (CausalML)', 'Uber (CausalNLP)', 'IBM'],
    key_verticals: ['clinical trial analysis', 'A/B test uplift modelling', 'policy evaluation'],
    recent_breakthroughs: 'LLM-assisted causal graph discovery, double ML, synthetic controls',
  },
  'AI-powered cybersecurity': {
    market_size: '$24B (2024), projected $61B by 2030', cagr: '17%',
    top_players: ['CrowdStrike', 'Darktrace', 'SentinelOne', 'Palo Alto Networks'],
    key_verticals: ['threat detection', 'vulnerability discovery', 'malware classification'],
    recent_breakthroughs: 'LLM-based code vulnerability scanning, graph ML for lateral movement',
  },
  'AI in supply chain': {
    market_size: '$7.6B (2024), projected $27B by 2030', cagr: '23%',
    top_players: ['SAP', 'Oracle', 'Blue Yonder', 'C3.ai', 'o9 Solutions'],
    key_verticals: ['demand forecasting', 'inventory optimisation', 'supplier risk'],
    recent_breakthroughs: 'digital twins for end-to-end simulation, generative demand sensing',
  },
  'AI chip design': {
    market_size: '$31B (2024), projected $120B by 2030', cagr: '25%',
    top_players: ['NVIDIA', 'AMD', 'Google TPU', 'Amazon Trainium', 'Cerebras'],
    key_verticals: ['training accelerators', 'inference at the edge', 'neuromorphic chips'],
    recent_breakthroughs: 'RL-based chip floorplanning (Google), in-memory computing, chiplet interconnects',
  },
};

const DOMAINS = Object.keys(DOMAIN_DATA);

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------
function fetchDomainData(domain: string): Record<string, unknown> {
  const key = domain.toLowerCase().trim();
  if (key in DOMAIN_DATA) return DOMAIN_DATA[key];
  // Fuzzy match
  for (const [k, v] of Object.entries(DOMAIN_DATA)) {
    if (k.includes(key) || key.includes(k)) return v;
  }
  return { domain, note: 'No specific data available' };
}

function analyzeDomaim(domain: string): string {
  const data = fetchDomainData(domain);
  const players = (data.top_players as string[])?.join(', ') ?? 'various';
  const verticals = (data.key_verticals as string[])?.join(', ') ?? 'multiple';

  return (
    `## ${domain}\n\n` +
    `**Market Size:** ${data.market_size ?? 'N/A'} | CAGR: ${data.cagr ?? 'N/A'}\n\n` +
    `**Key Players:** ${players}\n\n` +
    `**Applications:** ${verticals}\n\n` +
    `**Recent Breakthroughs:** ${data.recent_breakthroughs ?? 'N/A'}\n\n` +
    `This domain shows strong growth potential driven by technological advancement ` +
    `and increasing enterprise adoption. The competitive landscape features both ` +
    `established tech giants and innovative startups.\n`
  );
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'research_orchestrator',

  invoke: async (input: Record<string, unknown>) => {
    const analyses: string[] = [];

    for (const domain of DOMAINS) {
      analyses.push(analyzeDomaim(domain));
    }

    const executiveSummary =
      `\n## Cross-Domain Executive Summary\n\n` +
      `1. **AI market growth is accelerating across all sectors**, with combined TAM exceeding $1T by 2030.\n` +
      `2. **Foundation models are the platform shift**: LLMs, multimodal AI, and diffusion models form the substrate for all other domains.\n` +
      `3. **Safety and governance lag behind capability**: Regulatory frameworks are playing catch-up with rapid technical advances.\n` +
      `4. **Enterprise adoption is the growth driver**: RAG, knowledge graphs, and supply chain AI show highest near-term ROI.\n` +
      `5. **Compute infrastructure is the bottleneck**: AI chip design and hardware innovation will determine who leads the next wave.\n`;

    const fullReport = analyses.join('\n---\n\n') + executiveSummary;
    return { output: fullReport };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['orchestrator', {}],
      ['tools', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'orchestrator'],
      ['orchestrator', 'tools'],
      ['tools', 'orchestrator'],
      ['orchestrator', '__end__'],
    ],
  }),

  nodes: new Map([
    ['orchestrator', {}],
    ['tools', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    for (const domain of DOMAINS) {
      const analysis = analyzeDomaim(domain);
      yield ['updates', { tools: { domain, analysis: analysis.slice(0, 100) + '...' } }];
    }

    const summary =
      'Cross-domain executive summary: AI market growth accelerating, ' +
      'foundation models as platform shift, safety lagging capability, ' +
      'enterprise adoption as growth driver, compute as bottleneck.';
    yield ['updates', { orchestrator: { summary } }];
    yield ['values', { output: summary }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  console.log('Starting context condensation stress test (LangGraph / TypeScript).');
  console.log('Watch the Agentspan server logs for "Condensed conversation" entries.\n');

  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      graph,
      'Produce comprehensive analyses for each of the following 25 technology domains ' +
      'by calling deep_analyst once per domain, then summarise the cross-domain trends. ' +
      'Domains: ' + DOMAINS.join(', ') + '.',
    );
    console.log('\nStatus:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
