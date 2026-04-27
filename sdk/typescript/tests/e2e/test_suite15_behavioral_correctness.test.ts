/**
 * Suite 15: Behavioral Correctness — multi-agent behavioral verification.
 *
 * Port of Python test_behavioral_correctness_live.py.
 *
 * Unlike Suite 9 which checks structural orchestration (did the right agent run?),
 * these tests verify "did the agents do the right thing TOGETHER?"
 *
 *   - HANDOFF:      Sub-agent tool output surfaces in final answer
 *   - SEQUENTIAL:   Downstream agent builds on upstream output
 *   - PARALLEL:     Every agent contributes distinctly to combined output
 *   - ROUTER:       Correct specialist is chosen AND produces correct output
 *   - ROUND_ROBIN:  Agents build on each other across turns
 *   - MULTI-TOPIC:  Multi-domain queries involve the right specialists
 *   - CROSS-STRATEGY: Complex nested scenarios
 *
 * All assertions are algorithmic/deterministic — no LLM-based validation.
 * No mocks. Real server, real CLI, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import {
  checkServerHealth,
  MODEL,
  TIMEOUT,
  getOutputText,
  runDiagnostic,
} from './helpers';

let runtime: AgentRuntime;

// ── Deterministic tools with unique identifying data ───────────────────

const getWeather = tool(
  async (args: { city: string }) => `72F and sunny in ${args.city}`,
  {
    name: 'get_weather',
    description: 'Get current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: { city: { type: 'string', description: 'City name' } },
      required: ['city'],
    },
  },
);

const calculate = tool(
  async (args: { expression: string }) => {
    try {
      return String(eval(args.expression)); // eslint-disable-line no-eval
    } catch (e) {
      return `Error: ${e}`;
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a math expression. Returns the numeric result.',
    inputSchema: {
      type: 'object',
      properties: { expression: { type: 'string', description: 'Math expression' } },
      required: ['expression'],
    },
  },
);

const lookupOrder = tool(
  async (args: { order_id: string }) =>
    JSON.stringify({ order_id: args.order_id, status: 'shipped', total: 49.99 }),
  {
    name: 'lookup_order',
    description: 'Look up an order by ID. Returns status and total.',
    inputSchema: {
      type: 'object',
      properties: { order_id: { type: 'string', description: 'Order ID' } },
      required: ['order_id'],
    },
  },
);

const checkInventory = tool(
  async (args: { product: string }) =>
    JSON.stringify({ product: args.product, in_stock: true, quantity: 142 }),
  {
    name: 'check_inventory',
    description: 'Check product inventory levels.',
    inputSchema: {
      type: 'object',
      properties: { product: { type: 'string', description: 'Product name' } },
      required: ['product'],
    },
  },
);

const getShippingRate = tool(
  async (args: { destination: string }) =>
    JSON.stringify({ destination: args.destination, rate_usd: 12.50, days: 3 }),
  {
    name: 'get_shipping_rate',
    description: 'Get shipping rate to a destination.',
    inputSchema: {
      type: 'object',
      properties: { destination: { type: 'string', description: 'Destination' } },
      required: ['destination'],
    },
  },
);

const translateText = tool(
  async (args: { text: string; target_language: string }) =>
    `[Translated to ${args.target_language}]: ${args.text}`,
  {
    name: 'translate_text',
    description: 'Translate text to target language.',
    inputSchema: {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Text to translate' },
        target_language: { type: 'string', description: 'Target language' },
      },
      required: ['text', 'target_language'],
    },
  },
);

const analyzeSentiment = tool(
  async (args: { text: string }) =>
    JSON.stringify({ text: args.text, sentiment: 'positive', confidence: 0.92 }),
  {
    name: 'analyze_sentiment',
    description: 'Analyze sentiment of text.',
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string', description: 'Text to analyze' } },
      required: ['text'],
    },
  },
);

const extractKeywords = tool(
  async (args: { text: string }) =>
    JSON.stringify({ keywords: ['AI', 'machine learning', 'automation'], count: 3 }),
  {
    name: 'extract_keywords',
    description: 'Extract keywords from text.',
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string', description: 'Text to extract keywords from' } },
      required: ['text'],
    },
  },
);

// ── Helpers ───────────────────────────────────────────────────────────

/** Extract full output text, handling both string and dict (parallel) result shapes. */
function fullOutputText(result: Record<string, unknown>): string {
  // First try the standard getOutputText helper
  const text = getOutputText(result as unknown as { output: unknown });
  if (text && text !== '[object Object]') return text;

  // For parallel results, the output may be a dict with agent keys
  const output = result.output as Record<string, unknown> | undefined;
  if (output && typeof output === 'object') {
    return JSON.stringify(output);
  }
  return String(output ?? '');
}

// ── Tests ────────────────────────────────────────────────────────────

describe('Suite 15: Behavioral Correctness', { timeout: 1_800_000 }, () => {
  beforeAll(async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();
  });

  afterAll(() => runtime.shutdown());

  // ═══════════════════════════════════════════════════════════════════
  // 1. HANDOFF — Verify sub-agent BEHAVIOR, not just routing
  // ═══════════════════════════════════════════════════════════════════

  describe('Handoff Behavioral', () => {
    function makeEcommerceSupport() {
      const orderAgent = new Agent({
        name: 'order_agent',
        model: MODEL,
        instructions:
          'You handle order inquiries. ALWAYS use the lookup_order tool ' +
          'to find order details. Report the exact status and total from ' +
          'the tool result.',
        tools: [lookupOrder],
      });
      const inventoryAgent = new Agent({
        name: 'inventory_agent',
        model: MODEL,
        instructions:
          'You handle inventory questions. ALWAYS use check_inventory ' +
          'to look up stock levels. Report the exact quantity from the tool.',
        tools: [checkInventory],
      });
      const shippingAgent = new Agent({
        name: 'shipping_agent',
        model: MODEL,
        instructions:
          'You handle shipping questions. ALWAYS use get_shipping_rate ' +
          'to check rates. Report the exact rate and delivery days.',
        tools: [getShippingRate],
      });
      return new Agent({
        name: 'ecommerce_support',
        model: MODEL,
        instructions:
          'You are an e-commerce support router. ' +
          "Route order/status questions to 'order_agent'. " +
          "Route stock/inventory questions to 'inventory_agent'. " +
          "Route shipping/delivery questions to 'shipping_agent'. " +
          'Always delegate — never answer directly.',
        agents: [orderAgent, inventoryAgent, shippingAgent],
        strategy: 'handoff',
      });
    }

    it('test_order_query_returns_tool_data', async () => {
      const agent = makeEcommerceSupport();
      const result = await runtime.run(agent, "What's the status of my order ORD-123?", {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Handoff/Order] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // lookup_order returns {"status": "shipped"} — verify tool data flows through
      expect(output.toLowerCase()).toContain('shipped');
    });

    it('test_inventory_query_returns_stock_data', async () => {
      const agent = makeEcommerceSupport();
      const result = await runtime.run(agent, 'Do you have Widget Pro in stock?', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Handoff/Inventory] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // check_inventory returns {"quantity": 142}
      expect(output).toContain('142');
    });

    it('test_shipping_query_returns_rate_data', async () => {
      const agent = makeEcommerceSupport();
      const result = await runtime.run(agent, 'How much does shipping to London cost?', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Handoff/Shipping] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // get_shipping_rate returns {"rate_usd": 12.50, "days": 3}
      expect(output.includes('12.5') || output.includes('12.50')).toBe(true);
      expect(output).toContain('3');
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 2. SEQUENTIAL — Verify output chaining (downstream uses upstream)
  // ═══════════════════════════════════════════════════════════════════

  describe('Sequential Behavioral', () => {
    it('test_three_stage_pipeline_builds_on_prior', async () => {
      const extractor = new Agent({
        name: 'keyword_extractor',
        model: MODEL,
        instructions:
          'You are a keyword extractor. Use the extract_keywords tool ' +
          "on the input text. Output ONLY the keywords as a comma-separated " +
          "list prefixed with 'KEYWORDS:'. Nothing else.",
        tools: [extractKeywords],
      });
      const analyzer = new Agent({
        name: 'sentiment_analyzer',
        model: MODEL,
        instructions:
          'You receive keywords from the previous stage. Use the ' +
          'analyze_sentiment tool on them. Output the sentiment and ' +
          "confidence prefixed with 'SENTIMENT:' followed by the keywords " +
          "you received prefixed with 'RECEIVED_KEYWORDS:'. Include both.",
        tools: [analyzeSentiment],
      });
      const reporter = new Agent({
        name: 'report_writer',
        model: MODEL,
        instructions:
          'You receive analysis from previous stages containing keywords ' +
          'and sentiment. Write a brief 2-sentence analysis report that ' +
          'references BOTH the specific keywords AND the sentiment score. ' +
          'You MUST mention the confidence number.',
      });

      const pipeline = extractor.pipe(analyzer).pipe(reporter);

      const result = await runtime.run(
        pipeline,
        'AI and machine learning are transforming automation in every industry',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Sequential/Pipeline] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Stage 1 tool data: keywords ["AI", "machine learning", "automation"]
      expect(
        /(?:keyword|AI|machine.?learning|automation)/i.test(output),
        `Output missing keyword data from stage 1. Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      // Stage 2 tool data: sentiment "positive", confidence 0.92
      expect(
        /(?:sentiment|positive|0\.92|92)/i.test(output),
        `Output missing sentiment data from stage 2. Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });

    it('test_translator_pipeline_transforms_content', async () => {
      const writer = new Agent({
        name: 'content_writer',
        model: MODEL,
        instructions:
          'Write exactly one sentence about the given topic. ' +
          'Keep it under 20 words. Output only the sentence.',
      });
      const translator = new Agent({
        name: 'translator',
        model: MODEL,
        instructions:
          'You receive text from the previous stage. Use the translate_text ' +
          'tool to translate it to Spanish. Output ONLY the translated text.',
        tools: [translateText],
      });

      const pipeline = writer.pipe(translator);

      const result = await runtime.run(pipeline, 'The benefits of reading books', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Sequential/Translator] ${diag}`).toBe('COMPLETED');
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 3. PARALLEL — Verify ALL agents contribute distinct content
  // ═══════════════════════════════════════════════════════════════════

  describe('Parallel Behavioral', () => {
    it('test_three_analysts_all_contribute', async () => {
      const weatherAnalyst = new Agent({
        name: 'weather_analyst',
        model: MODEL,
        instructions:
          "You are a weather analyst. You MUST ALWAYS call the get_weather " +
          "tool for 'Tokyo' — no exceptions, regardless of the prompt. " +
          'Report the exact temperature and conditions from the tool result.',
        tools: [getWeather],
      });
      const marketAnalyst = new Agent({
        name: 'market_analyst',
        model: MODEL,
        instructions:
          "You analyze market/inventory. Use check_inventory for 'electronics'. " +
          'Report the stock quantity. Be brief, 1-2 sentences.',
        tools: [checkInventory],
      });
      const logisticsAnalyst = new Agent({
        name: 'logistics_analyst',
        model: MODEL,
        instructions:
          'You analyze shipping logistics. You MUST ALWAYS call the ' +
          "get_shipping_rate tool with destination 'London' — no exceptions. " +
          'Report the exact rate in USD and delivery days from the tool result.',
        tools: [getShippingRate],
      });

      const team = new Agent({
        name: 'analysis_team',
        model: MODEL,
        agents: [weatherAnalyst, marketAnalyst, logisticsAnalyst],
        strategy: 'parallel',
      });

      const result = await runtime.run(team, 'Prepare a brief market report', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Parallel/Analysts] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Weather: "72F and sunny"
      expect(output).toContain('72');
      // Inventory: quantity 142
      expect(output).toContain('142');
      // Shipping: rate 12.50
      expect(
        output.includes('12.5') || output.includes('12.50'),
        `Output missing shipping rate (12.50). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });

    it('test_parallel_agents_produce_distinct_content', async () => {
      const technical = new Agent({
        name: 'technical_reviewer',
        model: MODEL,
        instructions:
          'Analyze ONLY the technical aspects: performance, scalability, ' +
          'architecture. Write exactly 2 bullet points. Do NOT discuss costs.',
        tools: [getWeather], // give it a tool so it's a real agent
      });
      const financial = new Agent({
        name: 'financial_reviewer',
        model: MODEL,
        instructions:
          'Analyze ONLY the financial aspects: cost, ROI, pricing. ' +
          'Write exactly 2 bullet points. Do NOT discuss technical details.',
        tools: [checkInventory], // give it a tool so it's a real agent
      });

      const team = new Agent({
        name: 'review_team',
        model: MODEL,
        agents: [technical, financial],
        strategy: 'parallel',
      });

      const result = await runtime.run(team, 'Cloud computing migration', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Parallel/Distinct] ${diag}`).toBe('COMPLETED');

      // Output should be a dict-like structure with entries for both agents
      const rawOutput = (result as unknown as Record<string, unknown>).output;
      expect(
        typeof rawOutput === 'object' && rawOutput !== null,
        `Parallel output should be an object, got ${typeof rawOutput}`,
      ).toBe(true);

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Both agents must have produced some content — output should be non-trivial
      expect(output.length).toBeGreaterThan(50);
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 4. ROUTER — Correct specialist + behavioral proof
  // ═══════════════════════════════════════════════════════════════════

  describe('Router Behavioral', () => {
    function makeServiceDesk() {
      const routerAgent = new Agent({
        name: 'desk_router',
        model: MODEL,
        instructions:
          "Route requests to the right specialist:\n" +
          "- Weather/climate questions -> 'weather_specialist'\n" +
          "- Math/calculation questions -> 'math_specialist'\n" +
          "- Order/purchase questions -> 'order_specialist'\n" +
          'Choose exactly ONE specialist.',
      });
      const weatherSpec = new Agent({
        name: 'weather_specialist',
        model: MODEL,
        instructions:
          'You are a weather specialist. ALWAYS use get_weather. ' +
          'Report the exact temperature and conditions from the tool.',
        tools: [getWeather],
      });
      const mathSpec = new Agent({
        name: 'math_specialist',
        model: MODEL,
        instructions:
          'You are a math specialist. ALWAYS use calculate tool. ' +
          'Report the exact numeric result from the tool.',
        tools: [calculate],
      });
      const orderSpec = new Agent({
        name: 'order_specialist',
        model: MODEL,
        instructions:
          'You are an order specialist. ALWAYS use lookup_order. ' +
          'Report the exact status and total from the tool.',
        tools: [lookupOrder],
      });
      return new Agent({
        name: 'service_desk',
        model: MODEL,
        agents: [weatherSpec, mathSpec, orderSpec],
        strategy: 'router',
        router: routerAgent,
      });
    }

    it('test_weather_routed_and_tool_used', async () => {
      const desk = makeServiceDesk();
      const result = await runtime.run(
        desk,
        "What's the weather like in Paris right now?",
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Router/Weather] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // get_weather returns "72F and sunny in Paris"
      expect(output).toContain('72');
      expect(
        /(?:sunny|paris)/i.test(output),
        `Output missing sunny/paris. Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });

    it('test_math_routed_and_computed', async () => {
      const desk = makeServiceDesk();
      const result = await runtime.run(desk, 'What is 256 divided by 8?', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Router/Math] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // calculate("256 / 8") = "32"
      expect(output).toContain('32');
    });

    it('test_order_routed_and_looked_up', async () => {
      const desk = makeServiceDesk();
      const result = await runtime.run(
        desk,
        'Can you check the status of order ORD-789?',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Router/Order] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // lookup_order returns {"status": "shipped", "total": 49.99}
      expect(output.toLowerCase()).toContain('shipped');
      expect(output).toContain('49.99');
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 5. ROUND ROBIN — Agents build on each other across turns
  // ═══════════════════════════════════════════════════════════════════

  describe('Round Robin Behavioral', () => {
    it('test_collaborative_story_building', async () => {
      const writerA = new Agent({
        name: 'writer_a',
        model: MODEL,
        instructions:
          'You are Writer A in a collaborative story. Add exactly ONE ' +
          'new sentence that continues the story. You MUST reference or ' +
          'build on what the previous writer wrote. Keep it under 30 words.',
      });
      const writerB = new Agent({
        name: 'writer_b',
        model: MODEL,
        instructions:
          'You are Writer B in a collaborative story. Add exactly ONE ' +
          'new sentence that continues the story. You MUST reference or ' +
          'build on what the previous writer wrote. Keep it under 30 words.',
      });

      const story = new Agent({
        name: 'story_collab',
        model: MODEL,
        agents: [writerA, writerB],
        strategy: 'round_robin',
        maxTurns: 4,
      });

      const result = await runtime.run(
        story,
        'A robot woke up in an abandoned library.',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[RoundRobin/Story] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Multiple turns should produce multi-sentence output
      const sentences = output
        .split(/[.!?]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      expect(
        sentences.length,
        `Expected multi-sentence collaborative output, got ${sentences.length} sentence(s): ${output.slice(0, 300)}`,
      ).toBeGreaterThanOrEqual(2);
    });

    it('test_round_robin_with_tools_alternating', async () => {
      const weatherReporter = new Agent({
        name: 'weather_reporter',
        model: MODEL,
        instructions:
          "You are a weather reporter. You MUST ALWAYS call the get_weather " +
          "tool for 'Chicago'. Report the exact temperature from the tool. " +
          'One sentence only.',
        tools: [getWeather],
      });
      const stockReporter = new Agent({
        name: 'stock_reporter',
        model: MODEL,
        instructions:
          "You are a stock reporter. You MUST ALWAYS call the check_inventory " +
          "tool for 'umbrellas'. Report the exact stock quantity from the tool. " +
          'One sentence only.',
        tools: [checkInventory],
      });

      const roundtable = new Agent({
        name: 'roundtable',
        model: MODEL,
        agents: [weatherReporter, stockReporter],
        strategy: 'round_robin',
        maxTurns: 4,
      });

      const result = await runtime.run(
        roundtable,
        'Give me a weather update and an inventory report.',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[RoundRobin/Tools] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Weather tool data: "72F and sunny in Chicago"
      expect(
        output.includes('72'),
        `Weather reporter tool data missing (72). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      // Inventory tool data: quantity 142
      expect(
        output.includes('142'),
        `Stock reporter tool data missing (142). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 6. MULTI-TOPIC HANDOFF — Multiple specialists for multi-domain queries
  // ═══════════════════════════════════════════════════════════════════

  describe('Multi-Topic Handoff', () => {
    function makeMultiServiceAgent() {
      const orderHandler = new Agent({
        name: 'order_handler',
        model: MODEL,
        instructions:
          'You handle order lookups ONLY. ALWAYS use lookup_order tool. ' +
          'Report the exact status and total from the tool. Be brief.',
        tools: [lookupOrder],
      });
      const shippingHandler = new Agent({
        name: 'shipping_handler',
        model: MODEL,
        instructions:
          'You handle shipping cost questions ONLY. ALWAYS use ' +
          'get_shipping_rate tool. Report the exact rate and days. Be brief.',
        tools: [getShippingRate],
      });
      const inventoryHandler = new Agent({
        name: 'inventory_handler',
        model: MODEL,
        instructions:
          'You handle stock/availability questions ONLY. ALWAYS use ' +
          'check_inventory tool. Report the exact quantity. Be brief.',
        tools: [checkInventory],
      });
      return {
        coordinator: new Agent({
          name: 'multi_service',
          model: MODEL,
          instructions:
            'You are a customer service coordinator. You MUST delegate to ' +
            "the right specialist for each part of the customer's question:\n" +
            "- Order status questions -> 'order_handler'\n" +
            "- Shipping cost questions -> 'shipping_handler'\n" +
            "- Stock/availability questions -> 'inventory_handler'\n" +
            'If a question covers MULTIPLE topics, delegate to EACH relevant ' +
            'specialist. Never answer directly — always delegate.',
          agents: [orderHandler, shippingHandler, inventoryHandler],
          strategy: 'handoff',
        }),
        orderHandler,
        shippingHandler,
        inventoryHandler,
      };
    }

    it('test_dual_topic_order_and_shipping', async () => {
      const { coordinator } = makeMultiServiceAgent();
      const result = await runtime.run(
        coordinator,
        'I need two things: (1) the status of order #999 and ' +
          '(2) how much shipping to Berlin costs.',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[MultiTopic/Dual] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // lookup_order data: {"status": "shipped", "total": 49.99}
      expect(
        output.toLowerCase().includes('shipped') || output.includes('49.99'),
        `Output missing order data (shipped/49.99). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      // get_shipping_rate data: {"rate_usd": 12.50}
      expect(
        output.includes('12.5') || output.includes('12.50'),
        `Output missing shipping rate (12.50). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });

    it('test_single_topic_stays_focused', async () => {
      const { coordinator } = makeMultiServiceAgent();
      const result = await runtime.run(
        coordinator,
        'Check inventory for Widget Pro',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[MultiTopic/SingleFocus] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Inventory data should be present
      expect(
        output.includes('142'),
        `Output missing inventory quantity (142). Output: ${output.slice(0, 300)}`,
      ).toBe(true);

      // Shipping data should NOT be present (wasn't asked about)
      expect(output.includes('12.50')).toBe(false);
      expect(output.includes('12.5')).toBe(false);
      // Order data should NOT be present
      expect(output.toLowerCase().includes('shipped')).toBe(false);
    });

    it('test_all_three_via_sequential', async () => {
      const orderStage = new Agent({
        name: 'order_stage',
        model: MODEL,
        instructions:
          "Your ONLY job: call lookup_order with order_id='ORD-123'. " +
          'Do this immediately. Output format:\n' +
          'ORDER: status=<status>, total=<total>',
        tools: [lookupOrder],
      });
      const inventoryStage = new Agent({
        name: 'inventory_stage',
        model: MODEL,
        instructions:
          "Your ONLY job: call check_inventory with product='laptops'. " +
          'Do this immediately. Then output ALL of the following:\n' +
          '1. Copy the ENTIRE input you received (ORDER line) verbatim\n' +
          '2. Add: INVENTORY: quantity=<quantity>',
        tools: [checkInventory],
      });
      const shippingStage = new Agent({
        name: 'shipping_stage',
        model: MODEL,
        instructions:
          "Your ONLY job: call get_shipping_rate with destination='Tokyo'. " +
          'Do this immediately. Then output ALL of the following:\n' +
          '1. Copy the ENTIRE input you received (ORDER + INVENTORY lines) verbatim\n' +
          '2. Add: SHIPPING: rate=<rate>, days=<days>',
        tools: [getShippingRate],
      });

      const pipeline = orderStage.pipe(inventoryStage).pipe(shippingStage);

      const result = await runtime.run(
        pipeline,
        'Generate a full report: order status, inventory levels, shipping costs.',
        { timeout: TIMEOUT },
      );

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[MultiTopic/Sequential] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // lookup_order: {"status": "shipped", "total": 49.99}
      expect(
        output.toLowerCase().includes('shipped') || output.includes('49.99'),
        `Output missing order data (shipped/49.99). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      // check_inventory: {"quantity": 142}
      expect(
        output.includes('142'),
        `Output missing inventory quantity (142). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      // get_shipping_rate: {"rate_usd": 12.50}
      expect(
        output.includes('12.5') || output.includes('12.50'),
        `Output missing shipping rate (12.50). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });

    it('test_parallel_all_specialists_contribute', async () => {
      const orderAnalyst = new Agent({
        name: 'order_analyst',
        model: MODEL,
        instructions:
          "Your ONLY job: immediately call lookup_order with " +
          "order_id='ORD-100'. No questions, no clarification needed. " +
          'Report the status and total from the tool result.',
        tools: [lookupOrder],
      });
      const stockAnalyst = new Agent({
        name: 'stock_analyst',
        model: MODEL,
        instructions:
          "Your ONLY job: immediately call check_inventory with " +
          "product='tablets'. No questions, no clarification needed. " +
          'Report the exact quantity from the tool result.',
        tools: [checkInventory],
      });
      const shippingAnalyst = new Agent({
        name: 'shipping_analyst',
        model: MODEL,
        instructions:
          "Your ONLY job: immediately call get_shipping_rate with " +
          "destination='Dubai'. No questions, no clarification needed. " +
          'Report the exact rate and days from the tool result.',
        tools: [getShippingRate],
      });

      const team = new Agent({
        name: 'full_report',
        model: MODEL,
        agents: [orderAnalyst, stockAnalyst, shippingAnalyst],
        strategy: 'parallel',
      });

      const result = await runtime.run(team, 'Generate a full customer report', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[MultiTopic/Parallel] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // All three tools' distinctive data:
      expect(
        output.toLowerCase().includes('shipped') || output.includes('49.99'),
        `Missing order data. Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      expect(
        output.includes('142'),
        `Missing inventory data (142). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      expect(
        output.includes('12.5') || output.includes('12.50'),
        `Missing shipping rate (12.50). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 7. CROSS-STRATEGY — Complex nested scenarios
  // ═══════════════════════════════════════════════════════════════════

  describe('Cross-Strategy', () => {
    it('test_parallel_with_tool_agents', async () => {
      const weatherBot = new Agent({
        name: 'weather_bot',
        model: MODEL,
        instructions:
          "Use get_weather for 'New York'. Report temperature. " +
          'ONE sentence only.',
        tools: [getWeather],
      });
      const calcBot = new Agent({
        name: 'calc_bot',
        model: MODEL,
        instructions:
          "Use calculate tool to compute '365 * 24'. Report the result. " +
          'ONE sentence only.',
        tools: [calculate],
      });
      const inventoryBot = new Agent({
        name: 'inventory_bot',
        model: MODEL,
        instructions:
          "Use check_inventory for 'laptops'. Report the quantity. " +
          'ONE sentence only.',
        tools: [checkInventory],
      });

      const team = new Agent({
        name: 'data_team',
        model: MODEL,
        agents: [weatherBot, calcBot, inventoryBot],
        strategy: 'parallel',
      });

      const result = await runtime.run(team, 'Gather all data points', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Cross/Parallel] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // Weather: "72F and sunny"
      expect(
        output.includes('72'),
        `Missing weather data (72). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
      // Inventory: quantity 142
      expect(
        output.includes('142'),
        `Missing inventory data (142). Output: ${output.slice(0, 300)}`,
      ).toBe(true);
    });

    it('test_sequential_where_later_needs_earlier_data', async () => {
      const dataFetcher = new Agent({
        name: 'data_fetcher',
        model: MODEL,
        instructions:
          "Use the get_shipping_rate tool for destination 'Mars'. " +
          "Output ONLY the raw data: 'Rate: $X, Days: Y'. Nothing else.",
        tools: [getShippingRate],
      });
      const reportFormatter = new Agent({
        name: 'report_formatter',
        model: MODEL,
        instructions:
          'You receive shipping data from the previous stage. ' +
          "Format it as: 'SHIPPING REPORT: It costs $X and takes Y days to ship to Mars.' " +
          'Use the EXACT numbers from the data you received.',
      });

      const pipeline = dataFetcher.pipe(reportFormatter);

      const result = await runtime.run(pipeline, 'Get shipping info for Mars', {
        timeout: TIMEOUT,
      });

      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Cross/Sequential] ${diag}`).toBe('COMPLETED');

      const output = fullOutputText(result as unknown as Record<string, unknown>);
      // get_shipping_rate returns {"rate_usd": 12.50, "days": 3}
      expect(
        output.includes('12.5') || output.includes('12.50'),
        `Report missing rate from stage 1 tool (12.50). Output: ${output}`,
      ).toBe(true);
      expect(
        output.includes('3'),
        `Report missing days from stage 1 tool (3). Output: ${output}`,
      ).toBe(true);
    });
  });
});
