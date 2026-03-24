/**
 * LangGraph serializer — full extraction and graph-structure.
 *
 * Two serialization paths (tried in order):
 * 1. Full extraction — model + ToolNode tools → AI_MODEL + SIMPLE per tool
 * 2. Graph-structure — model found, custom StateGraph with nodes/edges
 *    → each node becomes a SIMPLE task, edges define workflow structure
 *
 * No passthrough fallback — throws ConfigurationError if extraction fails.
 */

import { ConfigurationError } from '../errors.js';
import type { WorkerInfo } from './serializer.js';

const _DEFAULT_NAME = 'langgraph_agent';

// ── Public API ──────────────────────────────────────────

/**
 * Serialize a LangGraph CompiledStateGraph into (rawConfig, WorkerInfo[]).
 *
 * @throws ConfigurationError if no model or tools can be extracted.
 */
export function serializeLangGraph(
  graph: unknown,
): [Record<string, unknown>, WorkerInfo[]] {
  const g = graph as Record<string, unknown>;
  const name = (typeof g.name === 'string' && g.name) || _DEFAULT_NAME;

  // Check for wrapper metadata first (set by @agentspan/sdk/langgraph wrapper)
  const metadata = g._agentspan as Record<string, unknown> | undefined;
  if (metadata?.model && metadata?.tools) {
    return _serializeFromMetadata(name, metadata);
  }

  // Try full extraction: find model and tools in the compiled graph
  const modelStr = _findModelInGraph(graph);
  const toolObjs = _findToolsInGraph(graph);

  if (modelStr && toolObjs.length > 0) {
    return _serializeFullExtraction(name, modelStr, toolObjs);
  }

  // Try graph-structure: extract nodes and edges
  const graphResult = _serializeGraphStructure(name, modelStr, graph);
  if (graphResult !== null) {
    return graphResult;
  }

  // Model found but graph-structure failed — use full extraction as pure LLM call
  if (modelStr) {
    const systemPrompt = _extractSystemPrompt(graph);
    return _serializeFullExtraction(name, modelStr, toolObjs, systemPrompt);
  }

  // No extraction possible — throw error
  throw new ConfigurationError(
    `Cannot extract from LangGraph graph. No model or tools detected. ` +
    `Use createReactAgent() or create a native agentspan Agent.`,
  );
}

// ── Wrapper metadata extraction ─────────────────────────

/**
 * Serialize from wrapper-captured metadata (set by @agentspan/sdk/langgraph).
 * Uses the model/tools/instructions stored on the graph by the wrapper.
 */
function _serializeFromMetadata(
  name: string,
  metadata: Record<string, unknown>,
): [Record<string, unknown>, WorkerInfo[]] {
  const modelStr = metadata.model as string;
  const tools = metadata.tools as unknown[];
  const instructions = metadata.instructions as string | undefined;

  const rawConfig: Record<string, unknown> = { name, model: modelStr };
  if (instructions) {
    rawConfig.instructions = instructions;
  }

  const toolDicts: Record<string, unknown>[] = [];
  const workers: WorkerInfo[] = [];

  for (const toolObj of tools) {
    const t = toolObj as Record<string, unknown>;
    const toolName = (typeof t.name === 'string' && t.name) || '';
    const description = (typeof t.description === 'string' && t.description) || '';
    const schema = _getToolSchema(toolObj);

    toolDicts.push({
      _worker_ref: toolName,
      description,
      parameters: schema,
    });

    const func = _getToolCallable(toolObj);
    if (func !== null) {
      workers.push({
        name: toolName,
        description: description.trim().split('\n')[0],
        inputSchema: schema,
        func,
      });
    }
  }

  rawConfig.tools = toolDicts;
  return [rawConfig, workers];
}

// ── Full extraction ─────────────────────────────────────

function _serializeFullExtraction(
  name: string,
  modelStr: string,
  toolObjs: unknown[],
  instructions?: string | null,
): [Record<string, unknown>, WorkerInfo[]] {
  const rawConfig: Record<string, unknown> = { name, model: modelStr };
  if (instructions) {
    rawConfig.instructions = instructions;
  }

  const toolDicts: Record<string, unknown>[] = [];
  const workers: WorkerInfo[] = [];

  for (const toolObj of toolObjs) {
    const t = toolObj as Record<string, unknown>;
    const toolName = (typeof t.name === 'string' && t.name) || '';
    const description = (typeof t.description === 'string' && t.description) || '';
    const schema = _getToolSchema(toolObj);

    toolDicts.push({
      _worker_ref: toolName,
      description,
      parameters: schema,
    });

    const func = _getToolCallable(toolObj);
    if (func !== null) {
      workers.push({
        name: toolName,
        description: description.trim().split('\n')[0],
        inputSchema: schema,
        func,
      });
    }
  }

  rawConfig.tools = toolDicts;
  return [rawConfig, workers];
}

// ── Graph-structure serialization ───────────────────────

function _serializeGraphStructure(
  name: string,
  modelStr: string | null,
  graph: unknown,
): [Record<string, unknown>, WorkerInfo[]] | null {
  const nodeFuncs = _extractNodeFunctions(graph);
  if (Object.keys(nodeFuncs).length === 0) return null;

  const [edges, conditionalEdges] = _extractEdges(graph);
  if (edges.length === 0 && conditionalEdges.length === 0) return null;

  const graphNodes: Record<string, unknown>[] = [];
  const workers: WorkerInfo[] = [];

  for (const [nodeName, func] of Object.entries(nodeFuncs)) {
    const workerName = `${name}_${nodeName}`;
    graphNodes.push({ name: nodeName, _worker_ref: workerName });
    workers.push({
      name: workerName,
      description: `Graph node '${nodeName}'`,
      inputSchema: { type: 'object', properties: { state: { type: 'object' } } },
      func,
    });
  }

  const graphEdges: Record<string, string>[] = [];
  for (const [src, tgt] of edges) {
    graphEdges.push({ source: src, target: tgt });
  }

  const graphConditional: Record<string, unknown>[] = [];
  for (const [src, routerFunc, targets] of conditionalEdges) {
    const routerName = `${name}_${src}_router`;
    graphConditional.push({
      source: src,
      _router_ref: routerName,
      targets,
    });
    workers.push({
      name: routerName,
      description: `Router for conditional edge from '${src}'`,
      inputSchema: { type: 'object', properties: { state: { type: 'object' } } },
      func: routerFunc,
    });
  }

  const rawConfig: Record<string, unknown> = {
    name,
    model: modelStr,
    _graph: {
      nodes: graphNodes,
      edges: graphEdges,
      conditional_edges: graphConditional,
    },
  };

  return [rawConfig, workers];
}

// ── Node/edge extraction ────────────────────────────────

function _extractNodeFunctions(graph: unknown): Record<string, Function> {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || !(nodes instanceof Map)) return {};

  const result: Record<string, Function> = {};
  for (const [nodeName, node] of nodes as Map<string, unknown>) {
    if (nodeName === '__start__' || nodeName === '__end__') continue;
    const func = _getNodeFunction(node);
    if (func !== null) {
      result[nodeName] = func;
    }
  }
  return result;
}

function _getNodeFunction(node: unknown): Function | null {
  if (typeof node !== 'object' || node === null) return null;
  const n = node as Record<string, unknown>;

  // LangGraph PregelNode has .bound.func
  const bound = n.bound as Record<string, unknown> | undefined;
  if (!bound) return null;
  const func = bound.func;
  if (typeof func !== 'function') return null;

  // Skip lambda/anonymous functions
  const funcName = func.name ?? '';
  if (!funcName || funcName === '' || funcName === 'anonymous') return null;

  return func as Function;
}

function _extractEdges(
  graph: unknown,
): [[string, string][], [string, Function, Record<string, string>][]] {
  const g = graph as Record<string, unknown>;
  const builder = g.builder as Record<string, unknown> | undefined;
  if (!builder) return [[], []];

  // Simple edges
  const edges: [string, string][] = [];
  const rawEdges = builder.edges;
  if (rawEdges instanceof Set) {
    for (const edge of rawEdges) {
      if (Array.isArray(edge) && edge.length === 2) {
        edges.push([String(edge[0]), String(edge[1])]);
      }
    }
  }

  // Conditional edges from builder.branches
  const conditional: [string, Function, Record<string, string>][] = [];
  const branches = builder.branches;
  if (branches && typeof branches === 'object') {
    for (const [srcNode, branchMap] of Object.entries(branches as Record<string, unknown>)) {
      if (typeof branchMap !== 'object' || branchMap === null) continue;
      for (const [, branchSpec] of Object.entries(branchMap as Record<string, unknown>)) {
        if (typeof branchSpec !== 'object' || branchSpec === null) continue;
        const spec = branchSpec as Record<string, unknown>;
        const path = spec.path as Record<string, unknown> | undefined;
        if (!path) continue;
        const routerFunc = path.func;
        if (typeof routerFunc !== 'function') continue;
        const targets = spec.ends;
        if (!targets || typeof targets !== 'object') continue;
        conditional.push([srcNode, routerFunc as Function, targets as Record<string, string>]);
      }
    }
  }

  return [edges, conditional];
}

// ── Model finding ───────────────────────────────────────

function _findModelInGraph(graph: unknown): string | null {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || !(nodes instanceof Map)) return null;

  // 1. Search node attributes (for createReactAgent-style graphs)
  for (const node of (nodes as Map<string, unknown>).values()) {
    const model = _searchForModel(node, 5);
    if (model) return model;
  }

  return null;
}

function _searchForModel(obj: unknown, depth: number): string | null {
  if (depth <= 0) return null;
  const result = _tryGetModelString(obj);
  if (result) return result;

  if (typeof obj !== 'object' || obj === null) return null;
  const asAny = obj as Record<string, unknown>;

  // Walk common nested property names
  for (const attr of ['bound', 'first', 'last', 'runnable', 'func']) {
    const child = asAny[attr];
    if (child != null && child !== obj) {
      const found = _searchForModel(child, depth - 1);
      if (found) return found;
    }
  }

  // Walk middle array
  const middle = asAny.middle;
  if (Array.isArray(middle)) {
    for (const child of middle) {
      const found = _searchForModel(child, depth - 1);
      if (found) return found;
    }
  }

  // Walk steps dict
  const steps = asAny.steps;
  if (steps && typeof steps === 'object' && !Array.isArray(steps)) {
    for (const child of Object.values(steps as Record<string, unknown>)) {
      const found = _searchForModel(child, depth - 1);
      if (found) return found;
    }
  }

  return null;
}

function _tryGetModelString(obj: unknown): string | null {
  if (typeof obj !== 'object' || obj === null) return null;
  const asAny = obj as Record<string, unknown>;
  const clsName = obj.constructor?.name ?? '';

  const modelName =
    (typeof asAny.model_name === 'string' && asAny.model_name) ||
    (typeof asAny.modelName === 'string' && asAny.modelName) ||
    (typeof asAny.model === 'string' && asAny.model) ||
    null;

  if (!modelName || modelName.length > 100) return null;
  if (modelName.startsWith('<') || modelName.startsWith('(')) return null;

  // Already has provider prefix
  if (modelName.includes('/')) return modelName;

  const provider = _inferProvider(clsName, modelName);
  return provider ? `${provider}/${modelName}` : modelName;
}

function _inferProvider(clsName: string, modelName: string): string | null {
  if (clsName.includes('OpenAI') || clsName.includes('openai')) return 'openai';
  if (clsName.includes('Anthropic') || clsName.includes('anthropic')) return 'anthropic';
  if (clsName.includes('Google') || clsName.includes('google')) return 'google';
  if (clsName.includes('Bedrock')) return 'bedrock';
  if (modelName.startsWith('gpt-') || modelName.startsWith('o1') || modelName.startsWith('o3') || modelName.startsWith('o4')) return 'openai';
  if (modelName.includes('claude')) return 'anthropic';
  if (modelName.includes('gemini')) return 'google';
  return null;
}

// ── Tool finding ────────────────────────────────────────

function _findToolsInGraph(graph: unknown): unknown[] {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || !(nodes instanceof Map)) return [];

  for (const node of (nodes as Map<string, unknown>).values()) {
    const tools = _searchForTools(node, 3);
    if (tools.length > 0) return tools;
  }
  return [];
}

function _searchForTools(obj: unknown, depth: number): unknown[] {
  if (depth <= 0) return [];
  if (typeof obj !== 'object' || obj === null) return [];
  const asAny = obj as Record<string, unknown>;

  // ToolNode has tools_by_name map
  const toolsByName = asAny.tools_by_name;
  if (toolsByName && typeof toolsByName === 'object') {
    if (toolsByName instanceof Map) {
      return Array.from(toolsByName.values());
    }
    if (!Array.isArray(toolsByName)) {
      return Object.values(toolsByName as Record<string, unknown>);
    }
  }

  // Recurse into common child properties
  for (const attr of ['bound', 'runnable', 'func']) {
    const child = asAny[attr];
    if (child != null && child !== obj) {
      const result = _searchForTools(child, depth - 1);
      if (result.length > 0) return result;
    }
  }
  return [];
}

// ── System prompt extraction ────────────────────────────

function _extractSystemPrompt(graph: unknown): string | null {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || !(nodes instanceof Map)) return null;

  for (const [nodeName, node] of nodes as Map<string, unknown>) {
    if (nodeName === '__start__' || nodeName === '__end__') continue;
    if (typeof node !== 'object' || node === null) continue;
    const n = node as Record<string, unknown>;

    // Look for system_prompt or system_message in the config
    const config = n.config as Record<string, unknown> | undefined;
    if (config) {
      const prompt = config.system_prompt ?? config.system_message ?? config.systemPrompt;
      if (typeof prompt === 'string') return prompt;
    }
  }

  return null;
}

// ── Tool schema/callable extraction ─────────────────────

function _getToolSchema(toolObj: unknown): Record<string, unknown> {
  if (typeof toolObj !== 'object' || toolObj === null) {
    return { type: 'object', properties: {} };
  }
  const t = toolObj as Record<string, unknown>;

  // LangChain BaseTool: args_schema (Pydantic model) → JSON schema
  if (t.args_schema && typeof t.args_schema === 'object') {
    const schema = t.args_schema as Record<string, unknown>;
    if (typeof schema.model_json_schema === 'function') {
      try {
        return (schema as any).model_json_schema();
      } catch {
        // fall through
      }
    }
  }

  // get_input_schema() method
  if (typeof t.get_input_schema === 'function') {
    try {
      const schema = (t as any).get_input_schema();
      if (typeof schema?.model_json_schema === 'function') {
        return schema.model_json_schema();
      }
    } catch {
      // fall through
    }
  }

  // Direct schema properties
  for (const key of ['params_json_schema', 'input_schema', 'parameters', 'schema']) {
    const val = t[key];
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      return val as Record<string, unknown>;
    }
  }

  return { type: 'object', properties: {} };
}

function _getToolCallable(toolObj: unknown): Function | null {
  if (typeof toolObj !== 'object' || toolObj === null) return null;
  const t = toolObj as Record<string, unknown>;

  // Direct func property
  if (typeof t.func === 'function') return t.func as Function;
  // _run method (LangChain tools)
  if (typeof t._run === 'function') return t._run as Function;
  // The tool itself might be callable
  if (typeof toolObj === 'function') return toolObj as Function;

  return null;
}
