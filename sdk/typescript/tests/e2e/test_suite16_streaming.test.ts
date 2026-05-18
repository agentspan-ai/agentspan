/**
 * Suite 16: Streaming — AgentStream API, event sequences, HITL flows, tools, guardrails.
 *
 * Ported from Python tests: test_e2e_sse.py + test_e2e_streaming.py
 *
 * All assertions are algorithmic/deterministic — no LLM-based validation.
 * No mocks — real server, real LLM, real streaming.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  AgentStream,
  tool,
  guardrail,
  RegexGuardrail,
} from '@agentspan-ai/sdk';
import type { AgentEvent, AgentResult, GuardrailResult } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL, TIMEOUT } from './helpers';

// ── Runtime setup ────────────────────────────────────────────────────────

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available — skipping e2e tests');
  runtime = new AgentRuntime();
});

afterAll(async () => {
  await runtime.shutdown();
});

// ── Unique name helper ───────────────────────────────────────────────────

let nameCounter = 0;
function uniqueName(prefix: string): string {
  nameCounter += 1;
  const ts = Date.now().toString(36);
  return `${prefix}_${ts}${nameCounter}`;
}

// ── Stream helper functions ──────────────────────────────────────────────

async function collectAllEvents(stream: AgentStream, timeoutMs = 120_000): Promise<AgentEvent[]> {
  const events: AgentEvent[] = [];
  const deadline = Date.now() + timeoutMs;
  for await (const event of stream) {
    events.push(event);
    if (Date.now() > deadline) break;
    if (event.type === 'done' || event.type === 'error') break;
  }
  return events;
}

async function collectEventsUntil(
  stream: AgentStream,
  stopType: string,
  timeoutMs = 120_000,
): Promise<AgentEvent[]> {
  const events: AgentEvent[] = [];
  const deadline = Date.now() + timeoutMs;
  for await (const event of stream) {
    events.push(event);
    if (event.type === stopType) break;
    if (Date.now() > deadline) break;
  }
  return events;
}

function eventTypes(events: AgentEvent[]): string[] {
  return events.map((e) => e.type);
}

function findEvents(events: AgentEvent[], type: string): AgentEvent[] {
  return events.filter((e) => e.type === type);
}

// ── Shared tools ─────────────────────────────────────────────────────────

const getWeather = tool(
  async (args: { city: string }) => ({ city: args.city, temp_f: 72, condition: 'sunny' }),
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

const getStockPrice = tool(
  async (args: { symbol: string }) => ({ symbol: args.symbol, price: 142.5, currency: 'USD' }),
  {
    name: 'get_stock_price',
    description: 'Get current stock price for a ticker symbol.',
    inputSchema: {
      type: 'object',
      properties: { symbol: { type: 'string', description: 'Ticker symbol' } },
      required: ['symbol'],
    },
  },
);

const publishArticle = tool(
  async (args: { title: string; body: string }) => ({
    status: 'published',
    title: args.title,
  }),
  {
    name: 'publish_article',
    description: 'Publish an article to the blog. Requires editorial approval.',
    approvalRequired: true,
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Article title' },
        body: { type: 'string', description: 'Article body' },
      },
      required: ['title', 'body'],
    },
  },
);

// ═══════════════════════════════════════════════════════════════════════════
// Category 1: Simple Agent Streaming
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — Simple Agent', { timeout: TIMEOUT }, () => {
  it('test_simple_agent_stream', async () => {
    const agent = new Agent({
      name: uniqueName('s16_simple'),
      model: MODEL,
      instructions: 'Reply with exactly one short sentence.',
    });
    const stream = await runtime.stream(agent, 'Say hello');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types).toContain('done');
    expect(events.length).toBeGreaterThanOrEqual(1);

    // Done event should have output
    const doneEvents = findEvents(events, 'done');
    expect(doneEvents.length).toBe(1);
    expect(doneEvents[0].output).not.toBeUndefined();
  });

  it('test_stream_execution_id_available', async () => {
    const agent = new Agent({
      name: uniqueName('s16_execid'),
      model: MODEL,
      instructions: 'Reply briefly.',
    });
    const stream = await runtime.stream(agent, 'Hi');
    // executionId is set in the constructor (via start()), available immediately
    expect(stream.executionId).toBeTruthy();
    await collectAllEvents(stream);
  });

  it('test_stream_get_result_after_events', async () => {
    const agent = new Agent({
      name: uniqueName('s16_result'),
      model: MODEL,
      instructions: 'Reply with exactly: OK',
    });
    const stream = await runtime.stream(agent, 'Go');
    await collectAllEvents(stream);

    const result = await stream.getResult();
    expect(result).not.toBeNull();
    expect(result.status).toBe('COMPLETED');
    expect(result.output).not.toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Category 2: Tool Agent Streaming
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — Tool Agent', { timeout: TIMEOUT }, () => {
  it('test_tool_agent_events', async () => {
    const agent = new Agent({
      name: uniqueName('s16_tools'),
      model: MODEL,
      instructions: 'Use the get_weather tool to find weather in London, then respond.',
      tools: [getWeather],
    });
    const stream = await runtime.stream(agent, 'What is the weather in London?');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types).toContain('done');

    // Should have at least one tool_call event
    const toolCalls = findEvents(events, 'tool_call');
    expect(toolCalls.length).toBeGreaterThanOrEqual(1);
  });

  it('test_multi_tool_agent', async () => {
    const agent = new Agent({
      name: uniqueName('s16_multi_tool'),
      model: MODEL,
      instructions: 'Use the appropriate tool to answer questions.',
      tools: [getWeather, getStockPrice],
    });
    const stream = await runtime.stream(agent, "What's AAPL trading at?");
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types).toContain('done');

    const doneEvents = findEvents(events, 'done');
    expect(doneEvents.length).toBe(1);
    expect(doneEvents[0].output).not.toBeUndefined();
  });

  it('test_tool_result_follows_call', async () => {
    const agent = new Agent({
      name: uniqueName('s16_tool_order'),
      model: MODEL,
      instructions: 'Use get_stock_price tool for AAPL, then answer.',
      tools: [getStockPrice],
    });
    const stream = await runtime.stream(agent, 'What is AAPL stock price?');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    // For every tool_call, there must be a subsequent tool_result
    for (let i = 0; i < types.length; i++) {
      if (types[i] === 'tool_call') {
        const remaining = types.slice(i + 1);
        expect(remaining).toContain('tool_result');
      }
    }
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Category 3: HITL Streaming
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — HITL', { timeout: TIMEOUT }, () => {
  it('test_hitl_approve_path', async () => {
    const agent = new Agent({
      name: uniqueName('s16_hitl_approve'),
      model: MODEL,
      instructions:
        'You are a blog writer. Write a very short article (one paragraph) ' +
        'about Python and publish it using the publish_article tool.',
      tools: [publishArticle],
    });
    const stream = await runtime.stream(agent, 'Write a short blog post about Python programming');

    // Collect until waiting
    const preEvents = await collectEventsUntil(stream, 'waiting', 120_000);
    const preTypes = eventTypes(preEvents);

    if (preTypes.includes('waiting')) {
      // Approve the pending action
      await stream.approve();
      // Stream is exhausted after the first for-await loop — poll status directly
      const deadline = Date.now() + 120_000;
      let status = await runtime.getStatus(stream.executionId);
      while (!status.isComplete && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1000));
        status = await runtime.getStatus(stream.executionId);
      }
      expect(['COMPLETED', 'FAILED', 'TERMINATED']).toContain(status.status);
    } else {
      // No waiting event — workflow completed without HITL (possible with some models)
      const terminalSeen = preTypes.includes('done') || preTypes.includes('error');
      if (!terminalSeen) {
        const status = await runtime.getStatus(stream.executionId);
        expect(status.isComplete).toBe(true);
      }
    }
  });

  it('test_hitl_reject_path', async () => {
    const agent = new Agent({
      name: uniqueName('s16_hitl_reject'),
      model: MODEL,
      instructions:
        'Write a very short article (one paragraph) about testing ' +
        'and publish it using publish_article.',
      tools: [publishArticle],
    });
    const stream = await runtime.stream(agent, 'Write about software testing');

    // Collect until waiting
    const preEvents = await collectEventsUntil(stream, 'waiting', 120_000);
    const preTypes = eventTypes(preEvents);

    if (preTypes.includes('waiting')) {
      // Reject the pending action
      await stream.reject('Does not meet editorial standards');
      // Stream is exhausted — poll status directly for terminal state
      const deadline = Date.now() + 120_000;
      let status = await runtime.getStatus(stream.executionId);
      while (!status.isComplete && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1000));
        status = await runtime.getStatus(stream.executionId);
      }
      expect(['COMPLETED', 'FAILED', 'TERMINATED']).toContain(status.status);
    } else {
      // No waiting event — workflow completed without HITL
      const terminalSeen = preTypes.includes('done') || preTypes.includes('error');
      if (!terminalSeen) {
        const status = await runtime.getStatus(stream.executionId);
        expect(status.isComplete).toBe(true);
      }
    }
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Category 4: Strategy Streaming (handoff, sequential, parallel, router)
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — Strategies', { timeout: TIMEOUT }, () => {
  it('test_handoff_stream', async () => {
    const mathAgent = new Agent({
      name: uniqueName('s16_math_sub'),
      model: MODEL,
      instructions: 'You are a math expert. Answer math questions concisely.',
    });
    const parent = new Agent({
      name: uniqueName('s16_handoff_parent'),
      model: MODEL,
      instructions: 'Delegate math questions to the math expert.',
      agents: [mathAgent],
      strategy: 'handoff',
    });
    const stream = await runtime.stream(parent, 'What is 7 * 8?');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types[types.length - 1]).toBe('done');
    expect(events.length).toBeGreaterThanOrEqual(2);
  });

  it('test_sequential_pipeline_stream', async () => {
    const summarizer = new Agent({
      name: uniqueName('s16_seq_sum'),
      model: MODEL,
      instructions: 'Summarize the input in one sentence.',
    });
    const translator = new Agent({
      name: uniqueName('s16_seq_trans'),
      model: MODEL,
      instructions: 'Translate the input to French.',
    });
    const pipeline = summarizer.pipe(translator);
    const stream = await runtime.stream(
      pipeline,
      'Python is a popular programming language used for web, AI, and scripting.',
    );
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types[types.length - 1]).toBe('done');
  });

  it('test_parallel_agents_stream', async () => {
    const analyst1 = new Agent({
      name: uniqueName('s16_par_a1'),
      model: MODEL,
      instructions: 'Analyze from a market perspective. Be brief.',
    });
    const analyst2 = new Agent({
      name: uniqueName('s16_par_a2'),
      model: MODEL,
      instructions: 'Analyze from a risk perspective. Be brief.',
    });
    const analysis = new Agent({
      name: uniqueName('s16_parallel'),
      model: MODEL,
      agents: [analyst1, analyst2],
      strategy: 'parallel',
    });
    const stream = await runtime.stream(analysis, 'Should we invest in AI startups?');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types[types.length - 1]).toBe('done');
  });

  it('test_router_stream', async () => {
    const planner = new Agent({
      name: uniqueName('s16_router_plan'),
      model: MODEL,
      instructions: 'Create a project plan. Be brief.',
    });
    const coder = new Agent({
      name: uniqueName('s16_router_code'),
      model: MODEL,
      instructions: 'Write code. Be brief.',
    });
    const routerAgent = new Agent({
      name: uniqueName('s16_router_lead'),
      model: MODEL,
      instructions: 'Select planner for planning tasks, coder for coding tasks.',
    });
    const team = new Agent({
      name: uniqueName('s16_router'),
      model: MODEL,
      agents: [planner, coder],
      strategy: 'router',
      router: routerAgent,
      maxTurns: 2,
    });
    const stream = await runtime.stream(team, 'Write a hello world function in Python');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types[types.length - 1]).toBe('done');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Category 5: Guardrail Streaming
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — Guardrails', { timeout: TIMEOUT }, () => {
  it('test_guardrail_pass_no_interference', async () => {
    const lenientGuardrail = guardrail(
      (_content: string): GuardrailResult => ({ passed: true }),
      {
        name: 'lenient',
        position: 'output',
        onFail: 'retry',
      },
    );
    const agent = new Agent({
      name: uniqueName('s16_guard_pass'),
      model: MODEL,
      instructions: 'Use get_weather to answer.',
      tools: [getWeather],
      guardrails: [lenientGuardrail],
    });
    const stream = await runtime.stream(agent, "What's the weather in Berlin?");
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    expect(types[types.length - 1]).toBe('done');
    expect(types).not.toContain('guardrail_fail');
  });

  it('test_guardrail_retry_stream', async () => {
    const noNumbersGuardrail = new RegexGuardrail({
      name: 'no_numbers',
      patterns: ['\\d+'],
      mode: 'block',
      position: 'output',
      onFail: 'retry',
      maxRetries: 3,
    });
    const agent = new Agent({
      name: uniqueName('s16_guard_retry'),
      model: MODEL,
      instructions: "Reply with the word 'hello' and nothing else.",
      guardrails: [noNumbersGuardrail],
    });
    const stream = await runtime.stream(agent, 'Greet me');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    // Should complete (pass or error after retries)
    const terminal = types[types.length - 1];
    expect(['done', 'error']).toContain(terminal);
  });

  it('test_regex_guardrail_events', async () => {
    const noEmailGuardrail = new RegexGuardrail({
      name: 'no_email',
      patterns: ['[\\w.+-]+@[\\w-]+\\.[\\w.-]+'],
      mode: 'block',
      position: 'output',
      onFail: 'retry',
      message: 'Response must not contain email addresses.',
      maxRetries: 3,
    });
    const agent = new Agent({
      name: uniqueName('s16_regex_guard'),
      model: MODEL,
      instructions: "Reply with the word 'hello' and nothing else.",
      guardrails: [noEmailGuardrail],
    });
    const stream = await runtime.stream(agent, 'Greet me');
    const events = await collectAllEvents(stream);

    const types = eventTypes(events);
    const terminal = types[types.length - 1];
    expect(['done', 'error']).toContain(terminal);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Category 6: Event Consistency
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — Event Consistency', { timeout: TIMEOUT }, () => {
  it('test_events_have_execution_id', async () => {
    const agent = new Agent({
      name: uniqueName('s16_execid_check'),
      model: MODEL,
      instructions: 'Reply briefly.',
    });
    const stream = await runtime.stream(agent, 'Hello');
    const events = await collectAllEvents(stream);

    // All events that have an executionId field should have a truthy value
    for (const event of events) {
      if ('executionId' in event && event.executionId !== undefined) {
        expect(event.executionId).toBeTruthy();
      }
    }
  });

  it('test_terminal_event_is_last', async () => {
    const agent = new Agent({
      name: uniqueName('s16_terminal'),
      model: MODEL,
      instructions: 'Reply with one word.',
    });
    const stream = await runtime.stream(agent, 'Go');
    const events = await collectAllEvents(stream);

    expect(events.length).toBeGreaterThanOrEqual(1);
    const lastType = events[events.length - 1].type;
    expect(['done', 'error']).toContain(lastType);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Category 7: Stream API
// ═══════════════════════════════════════════════════════════════════════════

describe('Suite 16: Streaming — Stream API', { timeout: TIMEOUT }, () => {
  it('test_stream_is_async_iterable', async () => {
    const agent = new Agent({
      name: uniqueName('s16_api_iter'),
      model: MODEL,
      instructions: 'Reply briefly.',
    });
    const stream = await runtime.stream(agent, 'Say hi.');

    // AgentStream implements AsyncIterable via Symbol.asyncIterator
    expect(typeof stream[Symbol.asyncIterator]).toBe('function');

    const events: AgentEvent[] = [];
    for await (const event of stream) {
      events.push(event);
      if (event.type === 'done' || event.type === 'error') break;
    }
    expect(events.length).toBeGreaterThanOrEqual(1);
  });

  it('test_stream_get_result_without_iteration', async () => {
    const agent = new Agent({
      name: uniqueName('s16_api_drain'),
      model: MODEL,
      instructions: 'Reply briefly.',
    });
    const stream = await runtime.stream(agent, 'Say hi.');

    // Don't iterate — just call getResult() which drains internally
    const result = await stream.getResult();
    expect(result).not.toBeNull();
    expect(result.output).not.toBeNull();
  });

  it('test_stream_handle', async () => {
    const agent = new Agent({
      name: uniqueName('s16_api_handle'),
      model: MODEL,
      instructions: 'Reply briefly.',
    });
    const stream = await runtime.stream(agent, 'Say hi.');

    // AgentStream exposes executionId and events
    expect(stream.executionId).toBeTruthy();
    expect(typeof stream.executionId).toBe('string');

    await collectAllEvents(stream);

    // After iteration, events array should be populated
    expect(stream.events.length).toBeGreaterThanOrEqual(1);
  });
});
