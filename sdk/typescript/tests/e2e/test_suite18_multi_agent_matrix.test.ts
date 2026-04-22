/**
 * Suite 18: Multi-Agent Matrix — 21 workflows covering all orchestration
 * strategies, tools, features, and composite patterns.
 *
 * All 21 workflows are fired concurrently in beforeAll, then polled round-robin
 * until completion or a 300 s global timeout.
 *
 * All validation is algorithmic — no LLM output parsing.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  tool,
  agentTool,
  OnTextMention,
  TextGate,
  TERMINAL_STATUSES,
} from '@agentspan-ai/sdk';
import type { AgentHandle, AgentResult } from '@agentspan-ai/sdk';
import {
  checkServerHealth,
  MODEL,
  getOutputText,
  runDiagnostic,
} from './helpers';

// ── Global constants ─────────────────────────────────────────────────────

const GLOBAL_TIMEOUT = 300_000; // 300 s for all 21 workflows

// ── Deterministic tools ──────────────────────────────────────────────────

const checkBalance = tool(
  async (args: { account_id: string }) => ({
    account_id: args.account_id,
    balance: 5432.10,
    currency: 'USD',
  }),
  {
    name: 'check_balance',
    description: 'Check account balance by account ID',
    inputSchema: {
      type: 'object',
      properties: {
        account_id: { type: 'string', description: 'The account identifier' },
      },
      required: ['account_id'],
    },
  },
);

const lookupOrder = tool(
  async (args: { order_id: string }) => ({
    order_id: args.order_id,
    status: 'shipped',
    eta: '2 days',
  }),
  {
    name: 'lookup_order',
    description: 'Look up order status by order ID',
    inputSchema: {
      type: 'object',
      properties: {
        order_id: { type: 'string', description: 'The order identifier' },
      },
      required: ['order_id'],
    },
  },
);

const getPricing = tool(
  async (args: { product: string }) => ({
    product: args.product,
    price: 99.99,
    discount: '10% off',
  }),
  {
    name: 'get_pricing',
    description: 'Get pricing information for a product',
    inputSchema: {
      type: 'object',
      properties: {
        product: { type: 'string', description: 'Product name' },
      },
      required: ['product'],
    },
  },
);

const collectData = tool(
  async (args: { source: string }) => ({
    source: args.source,
    records: 42,
    status: 'collected',
  }),
  {
    name: 'collect_data',
    description: 'Collect data from a specified source',
    inputSchema: {
      type: 'object',
      properties: {
        source: { type: 'string', description: 'Data source name' },
      },
      required: ['source'],
    },
  },
);

const analyzeData = tool(
  async (args: { data_summary: string }) => ({
    analysis: 'Trend is upward',
    confidence: 0.87,
  }),
  {
    name: 'analyze_data',
    description: 'Analyze a data summary and return trend analysis',
    inputSchema: {
      type: 'object',
      properties: {
        data_summary: { type: 'string', description: 'Summary of data to analyze' },
      },
      required: ['data_summary'],
    },
  },
);

const searchKB = tool(
  async (args: { query: string }) => ({
    query: args.query,
    result: args.query.toLowerCase().includes('python')
      ? 'Python is a versatile language'
      : 'Rust offers memory safety',
  }),
  {
    name: 'search_kb',
    description: 'Search the knowledge base for information',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
      },
      required: ['query'],
    },
  },
);

const calculate = tool(
  async (args: { expression: string }) => {
    try {
      const sanitized = args.expression.replace(/[^0-9+\-*/().]/g, '');
      const r = Function('"use strict"; return (' + sanitized + ')')();
      return { result: String(r) };
    } catch {
      return { error: 'invalid' };
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a mathematical expression',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'Math expression to evaluate' },
      },
      required: ['expression'],
    },
  },
);

// ── Test spec type ───────────────────────────────────────────────────────

interface TestSpec {
  testId: string;
  agent: Agent;
  prompt: string;
  validStatuses: string[];
  contains?: string;
}

interface TestResult {
  spec: TestSpec;
  status: string;
  output: string;
  executionId: string;
}

// ── Spec builder ─────────────────────────────────────────────────────────

function buildSpecs(): TestSpec[] {
  const specs: TestSpec[] = [];

  // ══════════════════════════════════════════════════════════════════════
  // Tier 1: Pure Strategies (7 tests)
  // ══════════════════════════════════════════════════════════════════════

  // #1: handoff_basic
  {
    const billing_t1 = new Agent({
      name: 'billing_t1',
      model: MODEL,
      instructions:
        'You are a billing agent. Use check_balance to look up account balances when asked. ' +
        'Always call the tool and report the result.',
      tools: [checkBalance],
    });
    const technical_t1 = new Agent({
      name: 'technical_t1',
      model: MODEL,
      instructions: 'You are a technical support agent. Help with technical issues.',
    });
    specs.push({
      testId: '#1_handoff_basic',
      agent: new Agent({
        name: 'e2e_matrix_handoff_basic',
        model: MODEL,
        instructions:
          'You route customer requests. For billing or account questions, delegate to billing_t1. ' +
          'For technical problems, delegate to technical_t1.',
        agents: [billing_t1, technical_t1],
        strategy: 'handoff',
      }),
      prompt: 'What is the balance on account ACC-123?',
      validStatuses: ['COMPLETED'],
    });
  }

  // #2: sequential_basic
  {
    const researcher = new Agent({
      name: 'researcher_t2',
      model: MODEL,
      instructions:
        'You are a researcher. Gather key facts and data about the given topic. ' +
        'Provide a structured summary of your findings.',
    });
    const writer = new Agent({
      name: 'writer_t2',
      model: MODEL,
      instructions:
        'You are a writer. Take the research provided and write a clear, concise article. ' +
        'Use the information from the previous step.',
    });
    const editor = new Agent({
      name: 'editor_t2',
      model: MODEL,
      instructions:
        'You are an editor. Review and polish the article. Fix grammar, improve clarity, ' +
        'and ensure the article flows well. Output the final version.',
    });
    specs.push({
      testId: '#2_sequential_basic',
      agent: researcher.pipe(writer).pipe(editor),
      prompt: 'The benefits of electric vehicles',
      validStatuses: ['COMPLETED'],
    });
  }

  // #3: parallel_basic
  {
    const market_t1 = new Agent({
      name: 'market_t1',
      model: MODEL,
      instructions:
        'You are a market analyst. Analyze the market opportunity and competitive landscape ' +
        'for the given product idea. Provide a structured assessment.',
    });
    const risk_t1 = new Agent({
      name: 'risk_t1',
      model: MODEL,
      instructions:
        'You are a risk analyst. Identify potential risks, challenges, and mitigation strategies ' +
        'for the given product idea. Provide a structured risk assessment.',
    });
    specs.push({
      testId: '#3_parallel_basic',
      agent: new Agent({
        name: 'e2e_matrix_parallel_basic',
        model: MODEL,
        instructions:
          'You orchestrate parallel analysis. Send the topic to both analysts simultaneously ' +
          'and combine their findings into a unified report.',
        agents: [market_t1, risk_t1],
        strategy: 'parallel',
      }),
      prompt: 'Evaluate launching a new mobile app.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #4: router_basic
  {
    const planner_t1 = new Agent({
      name: 'planner_t1',
      model: MODEL,
      instructions:
        'You are a routing agent. Analyze the request and route it. ' +
        'For planning tasks, route to planner_worker_t1. ' +
        'For coding tasks, route to coder_t1. ' +
        'For review tasks, route to reviewer_t1.',
    });
    const planner_worker_t1 = new Agent({
      name: 'planner_worker_t1',
      model: MODEL,
      instructions:
        'You are a project planner. Create detailed plans with milestones and timelines.',
    });
    const coder_t1 = new Agent({
      name: 'coder_t1',
      model: MODEL,
      instructions: 'You are a coder. Write clean, well-documented code.',
    });
    const reviewer_t1 = new Agent({
      name: 'reviewer_t1',
      model: MODEL,
      instructions: 'You are a code reviewer. Review code for bugs and improvements.',
    });
    specs.push({
      testId: '#4_router_basic',
      agent: new Agent({
        name: 'e2e_matrix_router_basic',
        model: MODEL,
        instructions: 'Route the request to the appropriate specialist.',
        agents: [planner_worker_t1, coder_t1, reviewer_t1],
        strategy: 'router',
        router: planner_t1,
      }),
      prompt: 'Create a plan for a REST API.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #5: round_robin_basic
  {
    const optimist = new Agent({
      name: 'optimist_t1',
      model: MODEL,
      instructions:
        'You are an optimist. Always argue the positive side of any topic. ' +
        'Be enthusiastic and highlight opportunities.',
    });
    const skeptic = new Agent({
      name: 'skeptic_t1',
      model: MODEL,
      instructions:
        'You are a skeptic. Always question assumptions and point out potential downsides. ' +
        'Be critical but constructive.',
    });
    specs.push({
      testId: '#5_round_robin_basic',
      agent: new Agent({
        name: 'e2e_matrix_rr_basic',
        model: MODEL,
        instructions: 'Facilitate a debate between optimist and skeptic.',
        agents: [optimist, skeptic],
        strategy: 'round_robin',
        maxTurns: 4,
      }),
      prompt: 'Should we invest in AI?',
      validStatuses: ['COMPLETED'],
    });
  }

  // #6: random_basic
  {
    const creative_a = new Agent({
      name: 'creative_a',
      model: MODEL,
      instructions: 'You are a creative thinker. Generate bold, innovative ideas.',
    });
    const creative_b = new Agent({
      name: 'creative_b',
      model: MODEL,
      instructions: 'You are a pragmatic thinker. Generate practical, actionable ideas.',
    });
    const creative_c = new Agent({
      name: 'creative_c',
      model: MODEL,
      instructions: 'You are a futurist. Generate forward-looking, visionary ideas.',
    });
    specs.push({
      testId: '#6_random_basic',
      agent: new Agent({
        name: 'e2e_matrix_random_basic',
        model: MODEL,
        instructions: 'Randomly select thinkers to brainstorm.',
        agents: [creative_a, creative_b, creative_c],
        strategy: 'random',
        maxTurns: 3,
      }),
      prompt: 'Brainstorm about the future.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #7: swarm_basic
  {
    const refund_agent = new Agent({
      name: 'refund_agent_t1',
      model: MODEL,
      instructions:
        'You are a refund specialist. Process refund requests and confirm the refund.',
    });
    const order_agent = new Agent({
      name: 'order_agent_t1',
      model: MODEL,
      instructions:
        'You are an order specialist. Look up order details and provide status updates.',
    });
    specs.push({
      testId: '#7_swarm_basic',
      agent: new Agent({
        name: 'e2e_matrix_swarm_basic',
        model: MODEL,
        instructions:
          'You are a customer service coordinator. Handle requests by delegating to the right agent.',
        agents: [refund_agent, order_agent],
        strategy: 'swarm',
        maxTurns: 3,
        handoffs: [
          new OnTextMention({ target: 'refund_agent_t1', text: 'refund' }),
          new OnTextMention({ target: 'order_agent_t1', text: 'order' }),
        ],
      }),
      prompt: 'I need a refund for order ORD-999.',
      validStatuses: ['COMPLETED'],
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // Tier 2: Strategies + Tools (4 tests)
  // ══════════════════════════════════════════════════════════════════════

  // #8: handoff_tools
  {
    const billing_t2 = new Agent({
      name: 'billing_t2',
      model: MODEL,
      instructions:
        'You are a billing agent. Use check_balance to check account balances. ' +
        'Always call the tool and include the balance in your response.',
      tools: [checkBalance],
    });
    const orders_t2 = new Agent({
      name: 'orders_t2',
      model: MODEL,
      instructions:
        'You are an orders agent. Use lookup_order to check order status. ' +
        'Always call the tool and include the order details in your response.',
      tools: [lookupOrder],
    });
    specs.push({
      testId: '#8_handoff_tools',
      agent: new Agent({
        name: 'e2e_matrix_handoff_tools',
        model: MODEL,
        instructions:
          'Route billing questions to billing_t2 and order questions to orders_t2.',
        agents: [billing_t2, orders_t2],
        strategy: 'handoff',
      }),
      prompt: 'What is the balance on account ACC-456?',
      validStatuses: ['COMPLETED'],
    });
  }

  // #9: sequential_tools
  {
    const collector = new Agent({
      name: 'collector_t2',
      model: MODEL,
      instructions:
        'You are a data collector. Use collect_data to gather data from the specified source. ' +
        'Always call the tool and report what was collected.',
      tools: [collectData],
    });
    const analyst = new Agent({
      name: 'analyst_t2',
      model: MODEL,
      instructions:
        'You are a data analyst. Use analyze_data to analyze the data summary you receive. ' +
        'Always call the tool and report the analysis findings.',
      tools: [analyzeData],
    });
    specs.push({
      testId: '#9_sequential_tools',
      agent: collector.pipe(analyst),
      prompt: 'Collect data from the sales database and analyze trends.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #10: parallel_tools
  {
    const balance_checker = new Agent({
      name: 'balance_checker_t2',
      model: MODEL,
      instructions:
        'You check account balances. Use check_balance for the account. Report the result.',
      tools: [checkBalance],
    });
    const order_checker = new Agent({
      name: 'order_checker_t2',
      model: MODEL,
      instructions:
        'You check order statuses. Use lookup_order for the order. Report the result.',
      tools: [lookupOrder],
    });
    specs.push({
      testId: '#10_parallel_tools',
      agent: new Agent({
        name: 'e2e_matrix_parallel_tools',
        model: MODEL,
        instructions:
          'Check the account balance and order status simultaneously. ' +
          'Combine and report both results.',
        agents: [balance_checker, order_checker],
        strategy: 'parallel',
      }),
      prompt: 'Check balance for ACC-789 and status of order ORD-111.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #11: swarm_tools
  {
    const billing_swarm = new Agent({
      name: 'billing_swarm_t2',
      model: MODEL,
      instructions:
        'You are a billing agent in a swarm. Use check_balance to look up balances. ' +
        'Always call the tool and include the exact balance in your response.',
      tools: [checkBalance],
    });
    const order_swarm = new Agent({
      name: 'order_swarm_t2',
      model: MODEL,
      instructions:
        'You are an orders agent in a swarm. Use lookup_order to check orders. ' +
        'Always call the tool and include order details.',
      tools: [lookupOrder],
    });
    specs.push({
      testId: '#11_swarm_tools',
      agent: new Agent({
        name: 'e2e_matrix_swarm_tools',
        model: MODEL,
        instructions:
          'You coordinate billing and order inquiries. Delegate to the appropriate agent.',
        agents: [billing_swarm, order_swarm],
        strategy: 'swarm',
        maxTurns: 4,
        handoffs: [
          new OnTextMention({ target: 'billing_swarm_t2', text: 'balance' }),
          new OnTextMention({ target: 'order_swarm_t2', text: 'order' }),
        ],
      }),
      prompt: 'What is the balance on account ACC-321?',
      validStatuses: ['COMPLETED'],
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // Tier 3: Strategy Features (3 tests)
  // ══════════════════════════════════════════════════════════════════════

  // #12: handoff_transitions — allowedTransitions
  {
    const collector_t3 = new Agent({
      name: 'collector_t3',
      model: MODEL,
      instructions:
        'You are a data collector. Gather information about the topic and pass it along. ' +
        'When done, mention that the analyst should review the data.',
      tools: [collectData],
    });
    const analyst_t3 = new Agent({
      name: 'analyst_t3',
      model: MODEL,
      instructions:
        'You are an analyst. Analyze the collected data and create findings. ' +
        'When done, mention the reporter should write the final report.',
      tools: [analyzeData],
    });
    const reporter_t3 = new Agent({
      name: 'reporter_t3',
      model: MODEL,
      instructions:
        'You are a reporter. Write a final summary report based on the analysis.',
    });
    specs.push({
      testId: '#12_handoff_transitions',
      agent: new Agent({
        name: 'e2e_matrix_handoff_transitions',
        model: MODEL,
        instructions:
          'You orchestrate a data pipeline: first collect data, then analyze, then report. ' +
          'Delegate to collector_t3 first.',
        agents: [collector_t3, analyst_t3, reporter_t3],
        strategy: 'handoff',
        allowedTransitions: {
          e2e_matrix_handoff_transitions: ['collector_t3'],
          collector_t3: ['analyst_t3'],
          analyst_t3: ['reporter_t3'],
        },
      }),
      prompt: 'Collect sales data, analyze trends, and write a report.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #13: sequential_gate — TextGate
  {
    const checker_t3 = new Agent({
      name: 'checker_t3',
      model: MODEL,
      instructions:
        'You are a code checker. Review the provided code for issues. ' +
        'If there are no issues at all, you MUST include the exact text "NO_ISSUES" in your response. ' +
        'If there are issues, describe them without saying "NO_ISSUES".',
      gate: new TextGate({ text: 'NO_ISSUES' }),
    });
    const fixer_t3 = new Agent({
      name: 'fixer_t3',
      model: MODEL,
      instructions:
        'You are a code fixer. Fix any issues identified by the checker. ' +
        'If no issues were found, confirm the code is clean.',
    });
    specs.push({
      testId: '#13_sequential_gate',
      agent: checker_t3.pipe(fixer_t3),
      prompt: 'Review this code: function add(a, b) { return a + b; }',
      validStatuses: ['COMPLETED'],
    });
  }

  // #14: round_robin_max_turns
  {
    const debater_a = new Agent({
      name: 'debater_a_t3',
      model: MODEL,
      instructions: 'You argue FOR remote work. Be concise — one paragraph max.',
    });
    const debater_b = new Agent({
      name: 'debater_b_t3',
      model: MODEL,
      instructions: 'You argue AGAINST remote work. Be concise — one paragraph max.',
    });
    specs.push({
      testId: '#14_round_robin_max_turns',
      agent: new Agent({
        name: 'e2e_matrix_rr_maxturns',
        model: MODEL,
        instructions: 'Facilitate a short debate (2 turns).',
        agents: [debater_a, debater_b],
        strategy: 'round_robin',
        maxTurns: 2,
      }),
      prompt: 'Is remote work better than in-office?',
      validStatuses: ['COMPLETED'],
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // Tier 4: Nested/Composite (6 tests)
  // ══════════════════════════════════════════════════════════════════════

  // #15: seq_then_parallel — parallel analysis >> summarizer
  {
    const market_t4 = new Agent({
      name: 'market_t4',
      model: MODEL,
      instructions: 'Analyze the market opportunity for the given idea. Be concise.',
    });
    const risk_t4 = new Agent({
      name: 'risk_t4',
      model: MODEL,
      instructions: 'Identify risks for the given idea. Be concise.',
    });
    const parallel_analysis = new Agent({
      name: 'parallel_analysis_t4',
      model: MODEL,
      instructions: 'Run market and risk analysis in parallel.',
      agents: [market_t4, risk_t4],
      strategy: 'parallel',
    });
    const summarizer_t4 = new Agent({
      name: 'summarizer_t4',
      model: MODEL,
      instructions:
        'Synthesize the market and risk analyses into a final executive summary.',
    });
    specs.push({
      testId: '#15_seq_then_parallel',
      agent: parallel_analysis.pipe(summarizer_t4),
      prompt: 'Evaluate a new AI-powered tutoring platform.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #16: seq_then_swarm — fetcher >> (coder <-> tester swarm)
  {
    const fetcher_t4 = new Agent({
      name: 'fetcher_t4',
      model: MODEL,
      instructions:
        'You are a requirements fetcher. Extract and summarize requirements from the request.',
    });
    const coder_t4 = new Agent({
      name: 'coder_t4',
      model: MODEL,
      instructions:
        'You are a coder. Write code based on requirements. If tests fail, fix the code.',
    });
    const tester_t4 = new Agent({
      name: 'tester_t4',
      model: MODEL,
      instructions:
        'You are a tester. Review the code and report whether it meets requirements.',
    });
    const swarm_dev = new Agent({
      name: 'swarm_dev_t4',
      model: MODEL,
      instructions: 'Coordinate coding and testing in a swarm.',
      agents: [coder_t4, tester_t4],
      strategy: 'swarm',
      maxTurns: 3,
      handoffs: [
        new OnTextMention({ target: 'coder_t4', text: 'code' }),
        new OnTextMention({ target: 'tester_t4', text: 'test' }),
      ],
    });
    specs.push({
      testId: '#16_seq_then_swarm',
      agent: fetcher_t4.pipe(swarm_dev),
      prompt: 'Build a function that computes Fibonacci numbers.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #17: handoff_to_parallel — handoff to quick_check OR parallel deep analysis
  {
    const quick_check_t4 = new Agent({
      name: 'quick_check_t4',
      model: MODEL,
      instructions: 'Do a quick, superficial check of the topic. One paragraph.',
    });
    const market_deep = new Agent({
      name: 'market_deep_t4',
      model: MODEL,
      instructions: 'Do a deep market analysis. Be thorough.',
    });
    const risk_deep = new Agent({
      name: 'risk_deep_t4',
      model: MODEL,
      instructions: 'Do a deep risk analysis. Be thorough.',
    });
    const deep_analysis = new Agent({
      name: 'deep_analysis_t4',
      model: MODEL,
      instructions: 'Run deep market and risk analysis in parallel.',
      agents: [market_deep, risk_deep],
      strategy: 'parallel',
    });
    specs.push({
      testId: '#17_handoff_to_parallel',
      agent: new Agent({
        name: 'e2e_matrix_handoff_to_parallel',
        model: MODEL,
        instructions:
          'You decide the depth of analysis needed. For simple questions, delegate to quick_check_t4. ' +
          'For complex strategic questions, delegate to deep_analysis_t4 for thorough parallel analysis.',
        agents: [quick_check_t4, deep_analysis],
        strategy: 'handoff',
      }),
      prompt: 'Should we enter the European market with our SaaS product?',
      validStatuses: ['COMPLETED'],
    });
  }

  // #18: router_to_sequential — router selects quick_answer OR pipeline
  {
    const router_lead_t4 = new Agent({
      name: 'router_lead_t4',
      model: MODEL,
      instructions:
        'You are a routing agent. For simple factual questions, route to quick_answer_t4. ' +
        'For complex research topics, route to research_pipeline_t4.',
    });
    const quick_answer_t4 = new Agent({
      name: 'quick_answer_t4',
      model: MODEL,
      instructions: 'Give a brief, direct answer to the question.',
    });
    const researcher_t4 = new Agent({
      name: 'researcher_t4',
      model: MODEL,
      instructions: 'Research the topic thoroughly and present key findings.',
    });
    const writer_t4 = new Agent({
      name: 'writer_t4',
      model: MODEL,
      instructions: 'Write a polished article based on the research provided.',
    });
    const research_pipeline = researcher_t4.pipe(writer_t4);
    specs.push({
      testId: '#18_router_to_sequential',
      agent: new Agent({
        name: 'e2e_matrix_router_to_seq',
        model: MODEL,
        instructions: 'Route to the appropriate handler based on complexity.',
        agents: [quick_answer_t4, research_pipeline],
        strategy: 'router',
        router: router_lead_t4,
      }),
      prompt: 'Write a detailed analysis of quantum computing applications in healthcare.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #19: swarm_hierarchical — CEO -> eng_team, mkt_team
  {
    const backend_eng = new Agent({
      name: 'backend_eng_t4',
      model: MODEL,
      instructions: 'You are a backend engineer. Discuss backend architecture decisions.',
    });
    const frontend_eng = new Agent({
      name: 'frontend_eng_t4',
      model: MODEL,
      instructions: 'You are a frontend engineer. Discuss UI/UX implementation.',
    });
    const eng_team = new Agent({
      name: 'eng_team_t4',
      model: MODEL,
      instructions:
        'You lead the engineering team. Coordinate backend and frontend engineers.',
      agents: [backend_eng, frontend_eng],
      strategy: 'handoff',
    });
    const content_mkt = new Agent({
      name: 'content_mkt_t4',
      model: MODEL,
      instructions: 'You create marketing content and messaging.',
    });
    const social_mkt = new Agent({
      name: 'social_mkt_t4',
      model: MODEL,
      instructions: 'You manage social media strategy and campaigns.',
    });
    const mkt_team = new Agent({
      name: 'mkt_team_t4',
      model: MODEL,
      instructions:
        'You lead the marketing team. Coordinate content and social marketing.',
      agents: [content_mkt, social_mkt],
      strategy: 'handoff',
    });
    specs.push({
      testId: '#19_swarm_hierarchical',
      agent: new Agent({
        name: 'e2e_matrix_ceo_swarm',
        model: MODEL,
        instructions:
          'You are the CEO. Delegate engineering tasks to eng_team_t4 and marketing tasks to mkt_team_t4.',
        agents: [eng_team, mkt_team],
        strategy: 'swarm',
        maxTurns: 3,
        handoffs: [
          new OnTextMention({ target: 'eng_team_t4', text: 'engineering' }),
          new OnTextMention({ target: 'mkt_team_t4', text: 'marketing' }),
        ],
      }),
      prompt: 'We need to launch a new product. Plan the engineering and marketing work.',
      validStatuses: ['COMPLETED'],
    });
  }

  // #20: parallel_tools_pipeline — (checkBalance || lookupOrder) >> summarizer
  {
    const balance_agent = new Agent({
      name: 'balance_agent_t4',
      model: MODEL,
      instructions:
        'Use check_balance to look up the account balance. Always call the tool and report the result.',
      tools: [checkBalance],
    });
    const order_agent_t4 = new Agent({
      name: 'order_agent_t4',
      model: MODEL,
      instructions:
        'Use lookup_order to check the order status. Always call the tool and report the result.',
      tools: [lookupOrder],
    });
    const parallel_lookup = new Agent({
      name: 'parallel_lookup_t4',
      model: MODEL,
      instructions: 'Look up balance and order status in parallel.',
      agents: [balance_agent, order_agent_t4],
      strategy: 'parallel',
    });
    const final_summarizer = new Agent({
      name: 'final_summarizer_t4',
      model: MODEL,
      instructions:
        'Combine the account balance and order status into a single customer summary.',
    });
    specs.push({
      testId: '#20_parallel_tools_pipeline',
      agent: parallel_lookup.pipe(final_summarizer),
      prompt: 'Check balance for ACC-555 and status of order ORD-777.',
      validStatuses: ['COMPLETED'],
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // Tier 5: Special (1 test)
  // ══════════════════════════════════════════════════════════════════════

  // #21: agent_tool_basic — Manager with agentTool(researcher) + calculate
  {
    const researcher_t5 = new Agent({
      name: 'researcher_t5',
      model: MODEL,
      instructions:
        'You are a research assistant. Answer questions about topics concisely.',
      tools: [searchKB],
    });
    specs.push({
      testId: '#21_agent_tool_basic',
      agent: new Agent({
        name: 'e2e_matrix_agent_tool',
        model: MODEL,
        instructions:
          'You are a manager agent with access to a researcher and a calculator. ' +
          'Use calculate to compute math expressions. Use researcher_t5 for knowledge questions. ' +
          'When asked to compute 2+2, call calculate with expression "2+2" and report the result.',
        tools: [agentTool(researcher_t5), calculate],
      }),
      prompt: 'What is 2+2? Use the calculator tool.',
      validStatuses: ['COMPLETED'],
      contains: '4',
    });
  }

  return specs;
}

// ── Concurrent launcher & poller ─────────────────────────────────────────

async function launchAndPollAll(
  runtime: AgentRuntime,
  specs: TestSpec[],
): Promise<Map<number, TestResult>> {
  const handles: { idx: number; handle: AgentHandle; spec: TestSpec }[] = [];

  // Launch all concurrently
  const launchPromises = specs.map(async (spec, idx) => {
    try {
      const handle = await runtime.start(spec.agent, spec.prompt);
      handles.push({ idx, handle, spec });
    } catch (err) {
      // If start itself fails, record immediately as FAILED
      handles.push({
        idx,
        handle: null as unknown as AgentHandle,
        spec,
      });
    }
  });
  await Promise.all(launchPromises);

  // Sort handles by index so results map is deterministic
  handles.sort((a, b) => a.idx - b.idx);

  const results = new Map<number, TestResult>();
  const pending = new Set<number>();

  for (const h of handles) {
    if (h.handle === null) {
      results.set(h.idx, {
        spec: h.spec,
        status: 'FAILED',
        output: '',
        executionId: '',
      });
    } else {
      pending.add(h.idx);
    }
  }

  const deadline = Date.now() + GLOBAL_TIMEOUT;

  // Poll round-robin until all complete or timeout
  while (pending.size > 0 && Date.now() < deadline) {
    for (const h of handles) {
      if (!pending.has(h.idx)) continue;
      try {
        const status = await h.handle.getStatus();
        if (TERMINAL_STATUSES.has(status.status)) {
          // Fetch result via wait() now that it's terminal (should return immediately)
          let output = '';
          try {
            const result = await h.handle.wait(100);
            output = getOutputText(result);
          } catch {
            // Fall back to status output
            output = String(status.output ?? '');
          }
          results.set(h.idx, {
            spec: h.spec,
            status: status.status,
            output,
            executionId: h.handle.executionId,
          });
          pending.delete(h.idx);
        }
      } catch {
        // Transient poll error — skip this iteration
      }
    }

    if (pending.size > 0) {
      await new Promise((r) => setTimeout(r, 2_000));
    }
  }

  // Mark remaining as TIMEOUT
  for (const idx of pending) {
    const h = handles.find((x) => x.idx === idx)!;
    results.set(idx, {
      spec: h.spec,
      status: 'TIMEOUT',
      output: '',
      executionId: h.handle?.executionId ?? '',
    });
  }

  return results;
}

// ── Assertion helper ─────────────────────────────────────────────────────

function checkResult(results: Map<number, TestResult>, num: number) {
  const r = results.get(num)!;
  expect(r, `Test ${num}: no result found`).toBeDefined();
  expect(
    r.status,
    `Test ${r.spec.testId}: got TIMEOUT (executionId=${r.executionId})`,
  ).not.toBe('TIMEOUT');
  expect(
    r.spec.validStatuses,
    `Test ${r.spec.testId}: got ${r.status} (executionId=${r.executionId})`,
  ).toContain(r.status);
  if (r.spec.contains && r.status === 'COMPLETED') {
    const outputLower = r.output.toLowerCase();
    const needle = r.spec.contains.toLowerCase();
    expect(
      outputLower,
      `Test ${r.spec.testId}: output missing "${r.spec.contains}" ` +
        `(executionId=${r.executionId}, output=${r.output.slice(0, 500)})`,
    ).toContain(needle);
  }
}

// ── Test suite ───────────────────────────────────────────────────────────

describe('Suite 18: Multi-Agent Matrix', { timeout: 1_800_000 }, () => {
  let runtime: AgentRuntime;
  let results: Map<number, TestResult>;

  beforeAll(async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();

    const specs = buildSpecs();
    expect(specs.length, 'Expected exactly 21 test specs').toBe(21);

    results = await launchAndPollAll(runtime, specs);
  }, 600_000); // 10 min for beforeAll (launch + poll)

  afterAll(() => runtime?.shutdown());

  // ── Tier 1: Pure Strategies ──────────────────────────────────────────

  it('#1 handoff_basic — routes to billing sub-agent', () => {
    checkResult(results, 0);
  });

  it('#2 sequential_basic — researcher >> writer >> editor pipeline', () => {
    checkResult(results, 1);
  });

  it('#3 parallel_basic — market + risk in parallel', () => {
    checkResult(results, 2);
  });

  it('#4 router_basic — router selects planner', () => {
    checkResult(results, 3);
  });

  it('#5 round_robin_basic — optimist vs skeptic debate', () => {
    checkResult(results, 4);
  });

  it('#6 random_basic — random selection of thinkers', () => {
    checkResult(results, 5);
  });

  it('#7 swarm_basic — swarm with OnTextMention', () => {
    checkResult(results, 6);
  });

  // ── Tier 2: Strategies + Tools ───────────────────────────────────────

  it('#8 handoff_tools — routing with balance check, tool called', () => {
    checkResult(results, 7);
  });

  it('#9 sequential_tools — collect >> analyze pipeline, completes', () => {
    checkResult(results, 8);
  });

  it('#10 parallel_tools — balance + order checked in parallel', () => {
    checkResult(results, 9);
  });

  it('#11 swarm_tools — swarm agents with tools, tool called', () => {
    checkResult(results, 10);
  });

  // ── Tier 3: Strategy Features ────────────────────────────────────────

  it('#12 handoff_transitions — collector > analyst > reporter chain', () => {
    checkResult(results, 11);
  });

  it('#13 sequential_gate — pipeline with TextGate', () => {
    checkResult(results, 12);
  });

  it('#14 round_robin_max_turns — debate capped at 2 turns', () => {
    checkResult(results, 13);
  });

  // ── Tier 4: Nested/Composite ─────────────────────────────────────────

  it('#15 seq_then_parallel — (market || risk) >> summarizer', () => {
    checkResult(results, 14);
  });

  it('#16 seq_then_swarm — fetcher >> coder/tester swarm', () => {
    checkResult(results, 15);
  });

  it('#17 handoff_to_parallel — handoff to quick_check OR deep parallel', () => {
    checkResult(results, 16);
  });

  it('#18 router_to_sequential — router selects quick OR research pipeline', () => {
    checkResult(results, 17);
  });

  it('#19 swarm_hierarchical — CEO > eng_team, mkt_team', () => {
    checkResult(results, 18);
  });

  it('#20 parallel_tools_pipeline — (balance || order) >> summarizer', () => {
    checkResult(results, 19);
  });

  // ── Tier 5: Special ──────────────────────────────────────────────────

  it('#21 agent_tool_basic — manager with agentTool + calculate, output contains 4', () => {
    checkResult(results, 20);
  });
});
