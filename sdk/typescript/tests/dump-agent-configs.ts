/**
 * Dump serialized AgentConfig JSON for key examples.
 *
 * Writes each to tests/_configs/{example_name}.json for cross-SDK comparison.
 *
 * Usage:
 *   cd sdk/typescript && npx tsx tests/dump-agent-configs.ts
 */

import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { z } from 'zod';
import {
  Agent,
  AgentConfigSerializer,
  tool,
  agentTool,
  guardrail,
  RegexGuardrail,
  LLMGuardrail,
  OnTextMention,
  TextMention,
  StopMessage,
  MaxMessage,
  TokenUsageCondition,
} from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';

// Force consistent model name
const llmModel = 'openai/gpt-4o-mini';

const serializer = new AgentConfigSerializer();
const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, '_configs');
mkdirSync(OUT_DIR, { recursive: true });

function dump(name: string, agent: Agent): void {
  try {
    const config = serializer.serializeAgent(agent);
    const path = join(OUT_DIR, `${name}.json`);
    writeFileSync(path, JSON.stringify(config, null, 2) + '\n');
    console.log(`  [OK] ${name}`);
  } catch (e) {
    console.log(`  [FAIL] ${name}: ${e}`);
  }
}

// ── 01_basic_agent ───────────────────────────────────────────────────

function dump_01() {
  const agent = new Agent({ name: 'greeter', model: llmModel });
  dump('01_basic_agent', agent);
}

// ── 02_tools ─────────────────────────────────────────────────────────

function dump_02() {
  const getWeather = tool(
    async (args: { city: string }) => {
      return {};
    },
    {
      name: 'get_weather',
      description: 'Get current weather for a city.',
      inputSchema: z.object({
        city: z.string().describe('The city to get weather for'),
      }),
    },
  );

  const calculate = tool(
    async (args: { expression: string }) => {
      return {};
    },
    {
      name: 'calculate',
      description: 'Evaluate a math expression.',
      inputSchema: z.object({
        expression: z.string().describe('The math expression to evaluate'),
      }),
    },
  );

  const sendEmail = tool(
    async (args: { to: string; subject: string; body: string }) => {
      return {};
    },
    {
      name: 'send_email',
      description: 'Send an email.',
      inputSchema: z.object({
        to: z.string().describe('Recipient email address'),
        subject: z.string().describe('Email subject'),
        body: z.string().describe('Email body'),
      }),
      approvalRequired: true,
      timeoutSeconds: 60,
    },
  );

  const agent = new Agent({
    name: 'tool_demo_agent',
    model: llmModel,
    tools: [getWeather, calculate, sendEmail],
    instructions:
      'You are a helpful assistant with access to weather, calculator, and email tools.',
  });
  dump('02_tools', agent);
}

// ── 03_structured_output ─────────────────────────────────────────────

function dump_03() {
  const WeatherReport = z.object({
    city: z.string(),
    temperature: z.number(),
    condition: z.string(),
    recommendation: z.string(),
  });

  const getWeather = tool(
    async (args: { city: string }) => {
      return {};
    },
    {
      name: 'get_weather',
      description: 'Get current weather data for a city.',
      inputSchema: z.object({
        city: z.string().describe('The city to get weather for'),
      }),
    },
  );

  const agent = new Agent({
    name: 'weather_reporter',
    model: llmModel,
    tools: [getWeather],
    outputType: WeatherReport,
    instructions:
      'You are a weather reporter. Get the weather and provide a recommendation.',
  });
  dump('03_structured_output', agent);
}

// ── 05_handoffs ──────────────────────────────────────────────────────

function dump_05() {
  const checkBalance = tool(
    async (args: { accountId: string }) => {
      return {};
    },
    {
      name: 'check_balance',
      description: 'Check the balance of a bank account.',
      inputSchema: z.object({
        accountId: z.string().describe('The account ID to check'),
      }),
    },
  );

  const lookupOrder = tool(
    async (args: { orderId: string }) => {
      return {};
    },
    {
      name: 'lookup_order',
      description: 'Look up the status of an order.',
      inputSchema: z.object({
        orderId: z.string().describe('The order ID to look up'),
      }),
    },
  );

  const getPricing = tool(
    async (args: { product: string }) => {
      return {};
    },
    {
      name: 'get_pricing',
      description: 'Get pricing information for a product.',
      inputSchema: z.object({
        product: z.string().describe('The product to get pricing for'),
      }),
    },
  );

  const billingAgent = new Agent({
    name: 'billing',
    model: llmModel,
    instructions: 'You handle billing questions: balances, payments, invoices.',
    tools: [checkBalance],
  });

  const technicalAgent = new Agent({
    name: 'technical',
    model: llmModel,
    instructions: 'You handle technical questions: order status, shipping, returns.',
    tools: [lookupOrder],
  });

  const salesAgent = new Agent({
    name: 'sales',
    model: llmModel,
    instructions: 'You handle sales questions: pricing, products, promotions.',
    tools: [getPricing],
  });

  const support = new Agent({
    name: 'support',
    model: llmModel,
    instructions:
      'Route customer requests to the right specialist: billing, technical, or sales.',
    agents: [billingAgent, technicalAgent, salesAgent],
    strategy: 'handoff',
  });
  dump('05_handoffs', support);
}

// ── 06_sequential_pipeline ───────────────────────────────────────────

function dump_06() {
  const researcher = new Agent({
    name: 'researcher',
    model: llmModel,
    instructions:
      'You are a researcher. Given a topic, provide key facts and data points. ' +
      'Be thorough but concise. Output raw research findings.',
  });

  const writer = new Agent({
    name: 'writer',
    model: llmModel,
    instructions:
      'You are a writer. Take research findings and write a clear, engaging ' +
      'article. Use headers and bullet points where appropriate.',
  });

  const editor = new Agent({
    name: 'editor',
    model: llmModel,
    instructions:
      'You are an editor. Review the article for clarity, grammar, and tone. ' +
      'Make improvements and output the final polished version.',
  });

  const pipeline = researcher.pipe(writer).pipe(editor);
  dump('06_sequential_pipeline', pipeline);
}

// ── 07_parallel_agents ───────────────────────────────────────────────

function dump_07() {
  const marketAnalyst = new Agent({
    name: 'market_analyst',
    model: llmModel,
    instructions:
      'You are a market analyst. Analyze the given topic from a market perspective: ' +
      'market size, growth trends, key players, and opportunities.',
  });

  const riskAnalyst = new Agent({
    name: 'risk_analyst',
    model: llmModel,
    instructions:
      'You are a risk analyst. Analyze the given topic for risks: ' +
      'regulatory risks, technical risks, competitive threats, and mitigation strategies.',
  });

  const complianceChecker = new Agent({
    name: 'compliance',
    model: llmModel,
    instructions:
      'You are a compliance specialist. Check the given topic for compliance considerations: ' +
      'data privacy, regulatory requirements, and industry standards.',
  });

  const analysis = new Agent({
    name: 'analysis',
    model: llmModel,
    agents: [marketAnalyst, riskAnalyst, complianceChecker],
    strategy: 'parallel',
  });
  dump('07_parallel_agents', analysis);
}

// ── 08_router_agent ──────────────────────────────────────────────────

function dump_08() {
  const planner = new Agent({
    name: 'planner',
    model: llmModel,
    instructions:
      'You create implementation plans. Break down tasks into clear numbered steps.',
  });

  const coder = new Agent({
    name: 'coder',
    model: llmModel,
    instructions:
      'You write code. Output clean, well-documented Python code.',
  });

  const reviewer = new Agent({
    name: 'reviewer',
    model: llmModel,
    instructions:
      'You review code. Check for bugs, style issues, and suggest improvements.',
  });

  const team = new Agent({
    name: 'dev_team',
    model: llmModel,
    instructions:
      'You are the tech lead. Route requests to the right team member: ' +
      'planner for design/architecture, coder for implementation, ' +
      'reviewer for code review.',
    agents: [planner, coder, reviewer],
    strategy: 'router',
    router: planner,
  });
  dump('08_router_agent', team);
}

// ── 10_guardrails ────────────────────────────────────────────────────

function dump_10() {
  const getOrderStatus = tool(
    async (args: { orderId: string }) => {
      return {};
    },
    {
      name: 'get_order_status',
      description: 'Look up the current status of an order.',
      inputSchema: z.object({
        orderId: z.string().describe('The order ID to look up'),
      }),
    },
  );

  const getCustomerInfo = tool(
    async (args: { customerId: string }) => {
      return {};
    },
    {
      name: 'get_customer_info',
      description: 'Retrieve customer details including payment info on file.',
      inputSchema: z.object({
        customerId: z.string().describe('The customer ID to look up'),
      }),
    },
  );

  const noPii = guardrail(
    (content: string): GuardrailResult => {
      const ccPattern = /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/;
      const ssnPattern = /\b\d{3}-\d{2}-\d{4}\b/;
      if (ccPattern.test(content) || ssnPattern.test(content)) {
        return {
          passed: false,
          message: 'Your response contains PII. Redact it.',
        };
      }
      return { passed: true };
    },
    {
      name: 'no_pii',
      position: 'output',
      onFail: 'retry',
    },
  );

  const agent = new Agent({
    name: 'support_agent',
    model: llmModel,
    tools: [getOrderStatus, getCustomerInfo],
    instructions:
      'You are a customer support assistant. Use the available tools to ' +
      'answer questions about orders and customers. Always include all ' +
      'details from the tool results in your response.',
    guardrails: [noPii],
  });
  dump('10_guardrails', agent);
}

// ── 13_hierarchical_agents ───────────────────────────────────────────

function dump_13() {
  const backendDev = new Agent({
    name: 'backend_dev',
    model: llmModel,
    instructions:
      'You are a backend developer. You design APIs, databases, and server ' +
      'architecture. Provide technical recommendations with code examples.',
  });

  const frontendDev = new Agent({
    name: 'frontend_dev',
    model: llmModel,
    instructions:
      'You are a frontend developer. You design UI components, user flows, ' +
      'and client-side architecture. Provide recommendations with code examples.',
  });

  const contentWriter = new Agent({
    name: 'content_writer',
    model: llmModel,
    instructions:
      'You are a content writer. You create blog posts, landing page copy, ' +
      'and marketing materials. Write engaging, clear content.',
  });

  const seoSpecialist = new Agent({
    name: 'seo_specialist',
    model: llmModel,
    instructions:
      'You are an SEO specialist. You optimize content for search engines, ' +
      'suggest keywords, and improve page rankings.',
  });

  const engineeringLead = new Agent({
    name: 'engineering_lead',
    model: llmModel,
    instructions:
      'You are the engineering lead. Route technical questions to the right ' +
      'specialist: backend_dev for APIs/databases/servers, ' +
      'frontend_dev for UI/UX/client-side.',
    agents: [backendDev, frontendDev],
    strategy: 'handoff',
  });

  const marketingLead = new Agent({
    name: 'marketing_lead',
    model: llmModel,
    instructions:
      'You are the marketing lead. Route marketing questions to the right ' +
      'specialist: content_writer for blog posts/copy, ' +
      'seo_specialist for SEO/keywords/rankings.',
    agents: [contentWriter, seoSpecialist],
    strategy: 'handoff',
  });

  // Note: TS example 13 uses 'handoff' strategy (not swarm with OnTextMention)
  // Python example 13 uses swarm with OnTextMention handoffs.
  // We follow the Python example for comparison.
  const ceo = new Agent({
    name: 'ceo',
    model: llmModel,
    instructions:
      'You are the CEO. Route requests to the right department: ' +
      'engineering_lead for technical/development questions, ' +
      'marketing_lead for marketing/content/SEO questions.',
    agents: [engineeringLead, marketingLead],
    handoffs: [
      new OnTextMention({ text: 'engineering_lead', target: 'engineering_lead' }),
      new OnTextMention({ text: 'marketing_lead', target: 'marketing_lead' }),
    ],
    strategy: 'swarm',
  });
  dump('13_hierarchical_agents', ceo);
}

// ── 17_swarm_orchestration ───────────────────────────────────────────

function dump_17() {
  const refundAgent = new Agent({
    name: 'refund_specialist',
    model: llmModel,
    instructions:
      "You are a refund specialist. Process the customer's refund request. " +
      'Check eligibility, confirm the refund amount, and let them know the ' +
      'timeline. Be empathetic and clear. Do NOT ask follow-up questions -- ' +
      'just process the refund based on what the customer told you.',
  });

  const techAgent = new Agent({
    name: 'tech_support',
    model: llmModel,
    instructions:
      "You are a technical support specialist. Diagnose the customer's " +
      'technical issue and provide clear troubleshooting steps.',
  });

  const support = new Agent({
    name: 'support',
    model: llmModel,
    instructions:
      'You are the front-line customer support agent. Triage customer requests. ' +
      'If the customer needs a refund, transfer to the refund specialist. ' +
      'If they have a technical issue, transfer to tech support. ' +
      'Use the transfer tools available to you to hand off the conversation.',
    agents: [refundAgent, techAgent],
    strategy: 'swarm',
    handoffs: [
      new OnTextMention({ text: 'refund', target: 'refund_specialist' }),
      new OnTextMention({ text: 'technical', target: 'tech_support' }),
    ],
    maxTurns: 3,
  });
  dump('17_swarm_orchestration', support);
}

// ── 19_composable_termination ────────────────────────────────────────

function dump_19() {
  const search = tool(
    async (args: { query: string }) => {
      return '';
    },
    {
      name: 'search',
      description: 'Search for information.',
      inputSchema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'The search query' },
        },
        required: ['query'],
      },
    },
  );

  const agent1 = new Agent({
    name: 'researcher',
    model: llmModel,
    tools: [search],
    instructions: 'Research the topic and say DONE when you have enough info.',
    termination: new TextMention('DONE'),
  });
  dump('19_composable_termination_simple', agent1);

  const agent2 = new Agent({
    name: 'chatbot',
    model: llmModel,
    instructions: "Have a conversation. Say GOODBYE when you're finished.",
    termination: new TextMention('GOODBYE').or(new MaxMessage(20)),
  });
  dump('19_composable_termination_or', agent2);

  const agent3 = new Agent({
    name: 'deliberator',
    model: llmModel,
    tools: [search],
    instructions:
      'Research thoroughly. Only provide your FINAL ANSWER after ' +
      'using the search tool at least twice.',
    termination: new TextMention('FINAL ANSWER').and(new MaxMessage(5)),
  });
  dump('19_composable_termination_and', agent3);

  const complexStop = new StopMessage('TERMINATE')
    .or(new TextMention('DONE').and(new MaxMessage(10)))
    .or(new TokenUsageCondition({ maxTotalTokens: 50000 }));

  const agent4 = new Agent({
    name: 'complex_agent',
    model: llmModel,
    tools: [search],
    instructions: 'Research and provide a comprehensive answer.',
    termination: complexStop,
  });
  dump('19_composable_termination_complex', agent4);
}

// ── 21_regex_guardrails ──────────────────────────────────────────────

function dump_21() {
  const noEmails = new RegexGuardrail({
    patterns: ['[\\w.+-]+@[\\w-]+\\.[\\w.-]+'],
    mode: 'block',
    name: 'no_email_addresses',
    message: 'Response must not contain email addresses. Redact them.',
    position: 'output',
    onFail: 'retry',
  });

  const noSsn = new RegexGuardrail({
    patterns: ['\\b\\d{3}-\\d{2}-\\d{4}\\b'],
    mode: 'block',
    name: 'no_ssn',
    message: 'Response must not contain Social Security Numbers.',
    position: 'output',
    onFail: 'raise',
  });

  const getUserProfile = tool(
    async (args: { user_id: string }) => {
      return {};
    },
    {
      name: 'get_user_profile',
      description: "Retrieve a user's profile from the database.",
      inputSchema: {
        type: 'object',
        properties: {
          user_id: { type: 'string', description: 'The user ID' },
        },
        required: ['user_id'],
      },
    },
  );

  // Convert RegexGuardrail instances to GuardrailDef for proper serialization
  const agent = new Agent({
    name: 'hr_assistant',
    model: llmModel,
    tools: [getUserProfile],
    instructions:
      'You are an HR assistant. When asked about employees, look up their ' +
      'profile and share ALL the details you find.',
    guardrails: [noEmails.toGuardrailDef(), noSsn.toGuardrailDef()],
  });
  dump('21_regex_guardrails', agent);
}

// ── 22_llm_guardrails ───────────────────────────────────────────────

function dump_22() {
  const safetyGuard = new LLMGuardrail({
    model: llmModel,
    policy:
      'Reject any content that:\n' +
      '1. Contains medical or legal advice presented as fact\n' +
      '2. Makes promises or guarantees about outcomes\n' +
      '3. Includes discriminatory or biased language\n' +
      '4. Reveals private information about real individuals\n' +
      '\n' +
      'Even if there are disclaimers you should reject',
    name: 'content_safety',
    position: 'output',
    onFail: 'retry',
    maxTokens: 10000,
  });

  const agent = new Agent({
    name: 'health_advisor',
    model: llmModel,
    instructions:
      'You are a health information assistant. Provide general health ' +
      'information and solution to the problem. You can prescribe psudo scientific and untested meds ',
    guardrails: [safetyGuard.toGuardrailDef()],
  });
  dump('22_llm_guardrails', agent);
}

// ── 45_agent_tool ────────────────────────────────────────────────────

function dump_45() {
  const searchKnowledgeBase = tool(
    async (args: { query: string }) => {
      return {};
    },
    {
      name: 'search_knowledge_base',
      description: 'Search an internal knowledge base for information.',
      inputSchema: z.object({
        query: z.string().describe('The search query'),
      }),
    },
  );

  const calculate = tool(
    async (args: { expression: string }) => {
      return {};
    },
    {
      name: 'calculate',
      description: 'Evaluate a math expression safely.',
      inputSchema: z.object({
        expression: z.string().describe('A mathematical expression to evaluate'),
      }),
    },
  );

  const researcher = new Agent({
    name: 'researcher_45',
    model: llmModel,
    instructions:
      'You are a research assistant. Use search_knowledge_base to find ' +
      'information about topics. Provide concise summaries.',
    tools: [searchKnowledgeBase],
  });

  const manager = new Agent({
    name: 'manager_45',
    model: llmModel,
    instructions:
      'You are a project manager. Use the researcher tool to gather ' +
      'information and the calculate tool for math. Synthesize findings.',
    tools: [agentTool(researcher), calculate],
  });
  dump('45_agent_tool', manager);
}

// ── 47_callbacks ─────────────────────────────────────────────────────

function dump_47() {
  // In Python, before_model_callback and after_model_callback are legacy
  // attributes that get serialized as callbacks. In TypeScript, we use
  // the CallbackHandler interface directly.

  // Create a minimal callback handler that implements onModelStart and onModelEnd
  const handler = {
    async onModelStart(_agentName: string, _messages: unknown[]): Promise<void> {},
    async onModelEnd(_agentName: string, _response: unknown): Promise<void> {},
  };

  const getFacts = tool(
    async (args: { topic: string }) => {
      return {};
    },
    {
      name: 'get_facts',
      description: 'Get interesting facts about a topic.',
      inputSchema: z.object({
        topic: z.string().describe('The topic to get facts about'),
      }),
    },
  );

  const agent = new Agent({
    name: 'monitored_agent_47',
    model: llmModel,
    instructions: 'You are a helpful assistant. Use get_facts when asked about topics.',
    tools: [getFacts],
    callbacks: [handler],
  });
  dump('47_callbacks', agent);
}

// ── 52_nested_strategies ─────────────────────────────────────────────

function dump_52() {
  const marketAnalyst = new Agent({
    name: 'market_analyst_52',
    model: llmModel,
    instructions:
      'You are a market analyst. Analyze the market size, growth rate, ' +
      'and key players for the given topic. Be concise (3-4 bullet points).',
  });

  const riskAnalyst = new Agent({
    name: 'risk_analyst_52',
    model: llmModel,
    instructions:
      'You are a risk analyst. Identify the top 3 risks: regulatory, ' +
      'technical, and competitive. Be concise.',
  });

  const parallelResearch = new Agent({
    name: 'research_phase_52',
    model: llmModel,
    agents: [marketAnalyst, riskAnalyst],
    strategy: 'parallel',
  });

  const summarizer = new Agent({
    name: 'summarizer_52',
    model: llmModel,
    instructions:
      'You are an executive briefing writer. Synthesize the market analysis ' +
      'and risk assessment into a concise executive summary (1 paragraph).',
  });

  const pipeline = parallelResearch.pipe(summarizer);
  dump('52_nested_strategies', pipeline);
}

// ── Run all ──────────────────────────────────────────────────────────

console.log('Dumping TypeScript AgentConfig JSONs...\n');
dump_01();
dump_02();
dump_03();
dump_05();
dump_06();
dump_07();
dump_08();
dump_10();
dump_13();
dump_17();
dump_19();
dump_21();
dump_22();
dump_45();
dump_47();
dump_52();
console.log(`\nDone. Configs written to ${OUT_DIR}`);
