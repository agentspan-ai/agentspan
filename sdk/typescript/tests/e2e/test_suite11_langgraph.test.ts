/**
 * Suite 11: LangGraph Integration — serialization and compilation.
 *
 * Tests that LangGraph graphs serialize correctly into Agentspan workflows:
 *   - Full extraction: createReactAgent → model + tools in rawConfig
 *   - Graph-structure: StateGraph → nodes + edges in rawConfig._graph
 *   - Tool extraction: tools have correct names, descriptions, schemas
 *   - Passthrough fallback: plain graph → single worker
 *   - Runtime execution: agent with tool produces correct output
 *
 * Uses serializeLangGraph() directly for compilation tests (no server needed).
 * Uses runtime.run() for the single execution test.
 *
 * All validation is algorithmic — structure assertions on serialized output.
 * Requires: @langchain/langgraph, @langchain/openai, @langchain/core
 * Skips if not installed.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { AgentRuntime } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL } from './helpers';

// ── Dynamic imports (skip if LangGraph not installed) ───────────────────

let langGraphAvailable = false;
let createReactAgent: any;
let ChatOpenAI: any;
let DynamicStructuredTool: any;
let StateGraph: any;
let START: any;
let END: any;
let Annotation: any;
let z: any;
let serializeLangGraph: any;
let detectFramework: any;

try {
  const lgPrebuilt = await import('@langchain/langgraph/prebuilt');
  createReactAgent = lgPrebuilt.createReactAgent;
  const lgCore = await import('@langchain/langgraph');
  StateGraph = lgCore.StateGraph;
  START = lgCore.START;
  END = lgCore.END;
  Annotation = lgCore.Annotation;
  const openai = await import('@langchain/openai');
  ChatOpenAI = openai.ChatOpenAI;
  const tools = await import('@langchain/core/tools');
  DynamicStructuredTool = tools.DynamicStructuredTool;
  const zod = await import('zod');
  z = zod.z;
  // Import the serializer directly for plan-only tests
  const lgSerializer = await import('../../src/frameworks/langgraph-serializer.js');
  serializeLangGraph = lgSerializer.serializeLangGraph;
  const detect = await import('../../src/frameworks/detect.js');
  detectFramework = detect.detectFramework;
  langGraphAvailable = true;
} catch {
  // LangGraph packages not installed — tests will be skipped
}

// ── Helpers ─────────────────────────────────────────────────────────────

let runtime: AgentRuntime;

let serverAvailable = false;

beforeAll(async () => {
  if (!langGraphAvailable) return;
  serverAvailable = await checkServerHealth();
  if (serverAvailable) {
    runtime = new AgentRuntime();
  }
});

afterAll(async () => {
  if (runtime) await runtime.shutdown();
});

// ── Tests ───────────────────────────────────────────────────────────────

describe('Suite 11: LangGraph Integration', { timeout: 300_000 }, () => {

  // ── 1. Framework detection ──────────────────────────────────────────

  it.skipIf(!langGraphAvailable)('framework detection identifies langgraph', () => {
    const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
    const graph = createReactAgent({ llm, tools: [], name: 'detect_test' });

    const framework = detectFramework(graph);
    expect(framework, 'detectFramework should return langgraph').toBe('langgraph');
  });

  // ── 2. Full extraction: ReAct agent with tools ──────────────────────

  it.skipIf(!langGraphAvailable)('full extraction — react agent with 3 tools', () => {
    const calculateTool = new DynamicStructuredTool({
      name: 'calculate',
      description: 'Evaluate a mathematical expression.',
      schema: z.object({ expression: z.string() }),
      func: async ({ expression }: { expression: string }) => String(eval(expression)),
    });

    const countWordsTool = new DynamicStructuredTool({
      name: 'count_words',
      description: 'Count words in text.',
      schema: z.object({ text: z.string() }),
      func: async ({ text }: { text: string }) => `${text.split(/\s+/).length} words`,
    });

    const reverseTool = new DynamicStructuredTool({
      name: 'reverse_text',
      description: 'Reverse a string.',
      schema: z.object({ text: z.string() }),
      func: async ({ text }: { text: string }) => text.split('').reverse().join(''),
    });

    const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
    const graph = createReactAgent({
      llm,
      tools: [calculateTool, countWordsTool, reverseTool],
      name: 'e2e_lg_react',
    });

    (graph as any)._agentspan = {
      model: 'openai/gpt-4o-mini',
      tools: [calculateTool, countWordsTool, reverseTool],
      framework: 'langgraph',
    };

    const [rawConfig, workers] = serializeLangGraph(graph);

    // Must be full extraction path (has model + tools)
    expect(rawConfig.model, '[FullExtract] model missing from rawConfig').toBeDefined();
    expect(
      String(rawConfig.model),
      '[FullExtract] wrong model',
    ).toContain('gpt-4o-mini');

    // Tools must be present with correct names
    const toolsList = rawConfig.tools as Record<string, unknown>[];
    expect(toolsList, '[FullExtract] tools missing').toBeDefined();
    expect(toolsList.length, '[FullExtract] expected 3 tools').toBe(3);

    const toolNames = toolsList.map((t) => t.name ?? t._worker_ref);
    expect(toolNames, '[FullExtract] calculate missing').toContain('calculate');
    expect(toolNames, '[FullExtract] count_words missing').toContain('count_words');
    expect(toolNames, '[FullExtract] reverse_text missing').toContain('reverse_text');

    // Each tool should have description
    for (const t of toolsList) {
      expect(t.description, `[FullExtract] tool ${t.name ?? t._worker_ref} missing description`).toBeTruthy();
    }

    // Workers should be extracted for each tool
    expect(workers.length, '[FullExtract] expected workers for tools').toBeGreaterThanOrEqual(3);
  });

  // ── 3. Tool schema extraction ───────────────────────────────────────

  it.skipIf(!langGraphAvailable)('tool schemas have correct parameters', () => {
    const multiplyTool = new DynamicStructuredTool({
      name: 'multiply',
      description: 'Multiply two numbers.',
      schema: z.object({
        a: z.number().describe('First number'),
        b: z.number().describe('Second number'),
      }),
      func: async ({ a, b }: { a: number; b: number }) => String(a * b),
    });

    const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
    const graph = createReactAgent({ llm, tools: [multiplyTool], name: 'e2e_lg_schema' });

    (graph as any)._agentspan = {
      model: 'openai/gpt-4o-mini',
      tools: [multiplyTool],
      framework: 'langgraph',
    };

    const [rawConfig] = serializeLangGraph(graph);
    const toolsList = rawConfig.tools as Record<string, unknown>[];
    expect(toolsList.length).toBeGreaterThanOrEqual(1);

    const multiply = toolsList.find((t) => (t.name ?? t._worker_ref) === 'multiply');
    expect(multiply, '[Schema] multiply tool not found').toBeDefined();
    expect(multiply!.description).toBe('Multiply two numbers.');

    // Parameters MUST be valid JSON Schema, NOT a raw Zod object.
    // The server expects {type: "object", properties: {a: ..., b: ...}}.
    const params = (multiply!.parameters ?? multiply!.inputSchema) as Record<string, unknown>;
    expect(params, '[Schema] no parameters on multiply tool').toBeDefined();

    // Must be JSON Schema (has "type" and "properties"), not Zod internal (_def, typeName)
    expect(
      params.type,
      `[Schema] parameters.type missing — got raw Zod object instead of JSON Schema. ` +
      `Keys: ${Object.keys(params)}`,
    ).toBe('object');
    expect(
      params.properties,
      '[Schema] parameters.properties missing — not a valid JSON Schema',
    ).toBeDefined();

    const props = params.properties as Record<string, unknown>;
    expect(props.a, '[Schema] missing property "a" in JSON Schema').toBeDefined();
    expect(props.b, '[Schema] missing property "b" in JSON Schema').toBeDefined();
  });

  // ── 4. Graph-structure: StateGraph nodes + edges ────────────────────

  it.skipIf(!langGraphAvailable)('stategraph — 3 nodes and edges extracted', () => {
    const QueryState = Annotation.Root({
      query: Annotation<string>({
        reducer: (_prev: string, next: string) => next ?? _prev,
        default: () => '',
      }),
      output: Annotation<string>({
        reducer: (_prev: string, next: string) => next ?? _prev,
        default: () => '',
      }),
    });

    function validate(state: any) { return { query: (state.query || '').trim() || 'default' }; }
    function process(state: any) { return { query: `processed:${state.query}` }; }
    function format(state: any) { return { output: `result:${state.query}` }; }

    const builder = new StateGraph(QueryState);
    builder.addNode('validate', validate);
    builder.addNode('process', process);
    builder.addNode('format', format);
    builder.addEdge(START, 'validate');
    builder.addEdge('validate', 'process');
    builder.addEdge('process', 'format');
    builder.addEdge('format', END);

    const graph = builder.compile({ name: 'e2e_lg_sg' });

    const [rawConfig, workers] = serializeLangGraph(graph);
    const configStr = JSON.stringify(rawConfig);

    // Graph-structure path should extract nodes
    // Check _graph.nodes if present, or check workers reference node names
    const graphData = rawConfig._graph as Record<string, unknown> | undefined;

    if (graphData) {
      // Graph-structure extraction succeeded
      const nodes = graphData.nodes as Record<string, unknown>[];
      expect(nodes, '[StateGraph] _graph.nodes missing').toBeDefined();
      expect(nodes.length, '[StateGraph] expected 3 nodes').toBeGreaterThanOrEqual(3);

      const nodeNames = nodes.map((n) => n.name as string);
      expect(nodeNames, '[StateGraph] validate missing').toContain('validate');
      expect(nodeNames, '[StateGraph] process missing').toContain('process');
      expect(nodeNames, '[StateGraph] format missing').toContain('format');

      // Edges should connect them
      const edges = graphData.edges as Record<string, unknown>[] | undefined;
      if (edges) {
        expect(edges.length, '[StateGraph] expected edges').toBeGreaterThanOrEqual(3);
      }
    } else {
      // Passthrough or full extraction fallback — nodes should still be referenced
      // Check that worker names contain node references
      const workerNames = workers.map((w) => w.name);
      expect(
        workerNames.some((n) => n.includes('validate')) ||
        configStr.includes('validate'),
        '[StateGraph] validate not found in config or workers',
      ).toBe(true);
    }
  });

  // ── 5. Passthrough fallback ─────────────────────────────────────────

  it.skipIf(!langGraphAvailable)('graph without metadata falls to passthrough', () => {
    const SimpleState = Annotation.Root({
      value: Annotation<string>({
        reducer: (_prev: string, next: string) => next ?? _prev,
        default: () => '',
      }),
    });

    const builder = new StateGraph(SimpleState);
    builder.addNode('echo', (state: any) => ({ value: `echo:${state.value}` }));
    builder.addEdge(START, 'echo');
    builder.addEdge('echo', END);

    const graph = builder.compile({ name: 'e2e_lg_passthrough' });
    // No _agentspan metadata → should fall to passthrough

    const [rawConfig, workers] = serializeLangGraph(graph);

    // Passthrough: should have _worker_name
    expect(
      rawConfig._worker_name ?? rawConfig.name,
      '[Passthrough] no worker name or graph name',
    ).toBeDefined();

    // Should have exactly 1 worker (the passthrough worker)
    expect(workers.length, '[Passthrough] expected 1 passthrough worker').toBe(1);
  });

  // ── 6. Runtime execution: tool produces deterministic output ────────

  it.skipIf(!langGraphAvailable || !process.env.OPENAI_API_KEY)('runtime execution — multiply tool returns 56', async () => {
    if (!serverAvailable) {
      console.log('Server not available — skipping runtime test');
      return;
    }

    const multiplyTool = new DynamicStructuredTool({
      name: 'multiply',
      description: 'Multiply two numbers and return the product.',
      schema: z.object({
        a: z.number().describe('First number'),
        b: z.number().describe('Second number'),
      }),
      func: async ({ a, b }: { a: number; b: number }) => String(a * b),
    });

    const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
    const graph = createReactAgent({
      llm,
      tools: [multiplyTool],
      name: 'e2e_lg_runtime',
    });

    (graph as any)._agentspan = {
      model: 'openai/gpt-4o-mini',
      tools: [multiplyTool],
      framework: 'langgraph',
    };

    const result = await runtime.run(graph, 'Multiply 7 by 8', { timeout: 120_000 });

    expect(result.executionId, '[Runtime] no executionId').toBeTruthy();
    expect(result.status, '[Runtime] not COMPLETED').toBe('COMPLETED');

    // Check output contains "56" (7*8=56) — deterministic tool output
    const outputStr = JSON.stringify(result.output);
    expect(
      outputStr.includes('56'),
      `[Runtime] output should contain "56". output=${outputStr.slice(0, 300)}`,
    ).toBe(true);
  });
});
