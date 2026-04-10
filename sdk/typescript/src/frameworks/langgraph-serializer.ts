/**
 * LangGraph serializer — full extraction, graph-structure, and passthrough.
 *
 * Three serialization paths (tried in order, matching Python SDK):
 * 1. Full extraction — model + ToolNode tools → AI_MODEL + SIMPLE per tool
 *    (createReactAgent graphs with known agent+tools structure)
 * 2. Graph-structure — custom StateGraph with nodes/edges, LLM/subgraph/human
 *    node detection, prep/finish workers, reducers, retry policies, input_key
 * 3. Passthrough — single SIMPLE task runs entire graph
 */

import type { WorkerInfo } from "./serializer.js";

const _DEFAULT_NAME = "langgraph_agent";

// Debug logging — set via _setDebugLog for testing/diagnostics
let _debugLog: ((...args: any[]) => void) | null = null;
/** @internal For debugging only. */
export function _setDebugLog(fn: ((...args: any[]) => void) | null) {
  _debugLog = fn;
}

// ── Public API ──────────────────────────────────────────

/**
 * Serialize a LangGraph CompiledStateGraph into (rawConfig, WorkerInfo[]).
 */
export function serializeLangGraph(
  graph: unknown,
  options?: { model?: unknown },
): [Record<string, unknown>, WorkerInfo[]] {
  const g = graph as Record<string, unknown>;
  const name = _extractGraphName(g);

  // Extract model hint from _agentspan metadata if present (but DON'T short-circuit)
  const metadata = g._agentspan as Record<string, unknown> | undefined;
  const metadataModel = metadata?.model as string | undefined;

  // Extract model from explicit option (LLM object or string passed via run()/deploy())
  const optionModel = options?.model != null ? _extractModelFromOption(options.model) : null;

  // Find model: explicit option > graph introspection > _agentspan metadata
  const modelStr = optionModel ?? _findModelInGraph(graph) ?? metadataModel ?? null;

  // Path 1: Full extraction — react agents with model + ToolNode (matching Python)
  // Requires BOTH model and tools. Python uses __closure__ to always find the model;
  // in JS, closures are sealed, so users must provide it via _agentspan metadata,
  // the wrapper import, or the model option in run()/deploy().
  const toolObjs = _findToolsInGraph(graph);
  if (modelStr && toolObjs.length > 0) {
    const instructions = metadata?.instructions as string | undefined;
    return _serializeFullExtraction(name, modelStr, toolObjs, instructions);
  }

  // Resolve the LLM object: explicit option > _agentspan.llm metadata
  // This is the actual LLM instance needed for monkey-patching .invoke()
  // in graph-structure prep/finish workers. Model string alone is not enough.
  const llmObj =
    options?.model != null && typeof options.model === "object"
      ? options.model
      : metadata?.llm != null && typeof metadata.llm === "object"
        ? metadata.llm
        : null;

  // Path 2: Graph-structure — custom StateGraph with nodes/edges
  const graphResult = _serializeGraphStructure(name, modelStr, graph, llmObj);
  if (graphResult !== null) {
    return graphResult;
  }

  // If metadata has tools, use metadata path (wrapper-created graph)
  if (metadata?.model && metadata?.tools) {
    return _serializeFromMetadata(name, metadata);
  }

  // Model found but no graph-structure or tools — use as pure LLM call
  if (modelStr) {
    const systemPrompt = _extractSystemPrompt(graph);
    return _serializeFullExtraction(name, modelStr, toolObjs, systemPrompt);
  }

  // Path 3: Passthrough — run entire graph in a single worker
  return _serializePassthrough(name);
}

// ── Graph name extraction ───────────────────────────────

function _extractGraphName(g: Record<string, unknown>): string {
  // Explicit name property
  if (typeof g.name === "string" && g.name) return g.name;
  // _agentspan metadata name
  const metadata = g._agentspan as Record<string, unknown> | undefined;
  if (metadata && typeof metadata.name === "string" && metadata.name) return metadata.name;
  // getName() method (LangGraph compiled graphs)
  // Filter out "LangGraph" — it's the generic default from Pregel, not user-defined.
  if (typeof (g as any).getName === "function") {
    try {
      const n = (g as any).getName();
      if (typeof n === "string" && n && n !== "LangGraph") return n;
    } catch {
      /* ignore */
    }
  }
  return _DEFAULT_NAME;
}

// ── Passthrough ─────────────────────────────────────────

function _serializePassthrough(name: string): [Record<string, unknown>, WorkerInfo[]] {
  const workerName = name;
  return [
    { name, _worker_name: workerName },
    [
      {
        name: workerName,
        description: `Passthrough worker for ${name}`,
        inputSchema: {},
        func: null,
      },
    ],
  ];
}

// ── Wrapper metadata extraction ─────────────────────────

function _serializeFromMetadata(
  name: string,
  metadata: Record<string, unknown>,
): [Record<string, unknown>, WorkerInfo[]] {
  const modelStr = metadata.model as string;
  const tools = metadata.tools as unknown[];
  const instructions = metadata.instructions as string | undefined;

  const rawConfig: Record<string, unknown> = { name, model: modelStr };
  if (instructions) rawConfig.instructions = instructions;

  const toolDicts: Record<string, unknown>[] = [];
  const workers: WorkerInfo[] = [];

  for (const toolObj of tools) {
    const t = toolObj as Record<string, unknown>;
    const toolName = (typeof t.name === "string" && t.name) || "";
    const description = (typeof t.description === "string" && t.description) || "";
    const schema = _getToolSchema(toolObj);

    toolDicts.push({ _worker_ref: toolName, description, parameters: schema });

    const func = _getToolCallable(toolObj);
    if (func !== null) {
      workers.push({
        name: toolName,
        description: description.trim().split("\n")[0],
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
  if (instructions) rawConfig.instructions = instructions;

  const toolDicts: Record<string, unknown>[] = [];
  const workers: WorkerInfo[] = [];

  for (const toolObj of toolObjs) {
    const t = toolObj as Record<string, unknown>;
    const toolName = (typeof t.name === "string" && t.name) || "";
    const description = (typeof t.description === "string" && t.description) || "";
    const schema = _getToolSchema(toolObj);

    toolDicts.push({ _worker_ref: toolName, description, parameters: schema });

    const func = _getToolCallable(toolObj);
    if (func !== null) {
      workers.push({
        name: toolName,
        description: description.trim().split("\n")[0],
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
  llmObjHint?: unknown,
): [Record<string, unknown>, WorkerInfo[]] | null {
  const nodeFuncs = _extractNodeFunctions(graph);
  if (Object.keys(nodeFuncs).length === 0) return null;

  const [edges, conditionalEdges] = _extractEdges(graph);
  if (edges.length === 0 && conditionalEdges.length === 0) return null;

  const graphNodes: Record<string, unknown>[] = [];
  const workers: WorkerInfo[] = [];

  for (const [nodeName, func] of Object.entries(nodeFuncs)) {
    const workerName = `${name}_${nodeName}`;

    // Human node: no worker needed, compiled as Conductor HUMAN task
    if (_isHumanNode(func)) {
      const humanPrompt = (func as any)._agentspan_human_prompt || "";
      graphNodes.push({
        name: nodeName,
        _worker_ref: workerName,
        _human_node: true,
        _human_prompt: humanPrompt,
      });
      continue;
    }

    // LLM node: detect LLM object referenced by this node
    const llmInfo = _findLLMInNode(func, graph, llmObjHint);
    if (llmInfo !== null) {
      const { llm: _llmObj, path: _llmPath } = llmInfo;
      const prepName = `${workerName}_prep`;
      const finishName = `${workerName}_finish`;

      graphNodes.push({
        name: nodeName,
        _worker_ref: workerName,
        _llm_node: true,
        _llm_prep_ref: prepName,
        _llm_finish_ref: finishName,
      });

      // Prep worker: captures llm.invoke() messages
      workers.push({
        name: prepName,
        description: `LLM prep for node '${nodeName}'`,
        inputSchema: { type: "object", properties: { state: { type: "object" } } },
        func: makeLLMPrepWorker(func, nodeName, _llmObj),
        _pre_wrapped: true,
        _extra: { llm_role: "prep" },
      });

      // Finish worker: re-runs node with mock LLM response
      workers.push({
        name: finishName,
        description: `LLM finish for node '${nodeName}'`,
        inputSchema: {
          type: "object",
          properties: { state: { type: "object" }, llm_result: { type: "string" } },
        },
        func: makeLLMFinishWorker(func, nodeName, _llmObj),
        _pre_wrapped: true,
        _extra: { llm_role: "finish" },
      });
      continue;
    }

    // Subgraph node: detect compiled graph referenced by this node
    const subgraphInfo = _findSubgraphInNode(func, graph, nodeName);
    if (subgraphInfo !== null) {
      const { subgraph: subgraphObj } = subgraphInfo;
      const prepName = `${workerName}_sg_prep`;
      const finishName = `${workerName}_sg_finish`;

      // Recursively serialize the subgraph
      const subName = `${name}_${nodeName}`;
      const subModel = _findModelInGraph(subgraphObj) ?? modelStr;
      const subResult = _serializeGraphStructure(subName, subModel, subgraphObj);

      if (subResult !== null) {
        const [subConfig, subWorkers] = subResult;
        (subConfig._graph as Record<string, unknown>)._is_subgraph = true;

        graphNodes.push({
          name: nodeName,
          _worker_ref: workerName,
          _subgraph_node: true,
          _subgraph_prep_ref: prepName,
          _subgraph_finish_ref: finishName,
          _subgraph_config: subConfig,
        });

        workers.push({
          name: prepName,
          description: `Subgraph prep for node '${nodeName}'`,
          inputSchema: { type: "object", properties: { state: { type: "object" } } },
          func: makeSubgraphPrepWorker(func, nodeName, subgraphObj),
          _pre_wrapped: true,
          _extra: { subgraph_role: "prep" },
        });

        workers.push({
          name: finishName,
          description: `Subgraph finish for node '${nodeName}'`,
          inputSchema: {
            type: "object",
            properties: { state: { type: "object" }, subgraph_result: { type: "object" } },
          },
          func: makeSubgraphFinishWorker(func, nodeName, subgraphObj),
          _pre_wrapped: true,
          _extra: { subgraph_role: "finish" },
        });

        workers.push(...subWorkers);
        continue;
      }
      // Subgraph extraction failed — fall through to regular node
    }

    // Regular node: single worker
    graphNodes.push({ name: nodeName, _worker_ref: workerName });
    workers.push({
      name: workerName,
      description: `Graph node '${nodeName}'`,
      inputSchema: { type: "object", properties: { state: { type: "object" } } },
      func: makeNodeWorker(func, nodeName),
      _pre_wrapped: true,
    });
  }

  // Simple edges
  const graphEdges: Record<string, string>[] = [];
  for (const [src, tgt] of edges) {
    graphEdges.push({ source: src, target: tgt });
  }

  // Collect dynamic fanout targets (need direct workers for FORK_JOIN_DYNAMIC)
  const dynamicFanoutTargets = new Set<string>();

  // Conditional edges
  const graphConditional: Record<string, unknown>[] = [];
  for (const [src, routerFunc, targets, isDynamic] of conditionalEdges) {
    const routerName = `${name}_${src}_router`;
    const ceEntry: Record<string, unknown> = {
      source: src,
      _router_ref: routerName,
      targets,
    };
    if (isDynamic) {
      ceEntry._dynamic_fanout = true;
      for (const targetNode of Object.values(targets)) {
        if (targetNode !== "__end__") {
          dynamicFanoutTargets.add(targetNode);
        }
      }
    }
    graphConditional.push(ceEntry);
    workers.push({
      name: routerName,
      description: `Router for conditional edge from '${src}'`,
      inputSchema: { type: "object", properties: { state: { type: "object" } } },
      func: makeRouterWorker(routerFunc, routerName, isDynamic),
      _pre_wrapped: true,
      _extra: { is_dynamic_fanout: isDynamic },
    });
  }

  // Register direct workers for dynamic fanout targets that are LLM nodes
  const existingNames = new Set(workers.map((w) => w.name));
  for (const targetNode of dynamicFanoutTargets) {
    const func = nodeFuncs[targetNode];
    if (!func) continue;
    const workerName = `${name}_${targetNode}`;
    if (!existingNames.has(workerName)) {
      workers.push({
        name: workerName,
        description: `Direct worker for dynamic fanout node '${targetNode}'`,
        inputSchema: { type: "object", properties: { state: { type: "object" } } },
        func: makeNodeWorker(func, targetNode),
        _pre_wrapped: true,
        _extra: { direct_node_worker: true },
      });
    }
  }

  const graphConfig: Record<string, unknown> = {
    nodes: graphNodes,
    edges: graphEdges,
    conditional_edges: graphConditional,
  };

  // Extract input_key from input schema
  const inputKey = _extractInputKey(graph);
  if (inputKey) graphConfig.input_key = inputKey;

  // Extract state reducers
  const reducers = _extractReducers(graph);
  if (reducers) graphConfig._reducers = reducers;

  // Extract retry policies
  const retryPolicies = _extractRetryPolicies(graph);
  if (retryPolicies) graphConfig._retry_policies = retryPolicies;

  const rawConfig: Record<string, unknown> = {
    name,
    model: modelStr,
    _graph: graphConfig,
  };

  return [rawConfig, workers];
}

// ── Node/edge extraction ────────────────────────────────

function _extractNodeFunctions(graph: unknown): Record<string, Function> {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || typeof nodes !== "object") return {};

  const result: Record<string, Function> = {};

  // Handle both Map and plain object
  const entries: [string, unknown][] =
    nodes instanceof Map ? Array.from(nodes.entries()) : Object.entries(nodes);

  for (const [nodeName, node] of entries) {
    if (nodeName === "__start__" || nodeName === "__end__") continue;
    const func = _getNodeFunction(node);
    if (func !== null) {
      result[nodeName] = func;
    }
  }
  return result;
}

function _getNodeFunction(node: unknown): Function | null {
  if (typeof node !== "object" || node === null) return null;
  const n = node as Record<string, unknown>;

  // LangGraph PregelNode has .bound.func (or .bound.afunc for async)
  const bound = n.bound as Record<string, unknown> | undefined;
  if (!bound) return null;
  const func = bound.func ?? bound.afunc;
  if (typeof func !== "function") return null;

  return func as Function;
}

function _extractEdges(
  graph: unknown,
): [[string, string][], [string, Function, Record<string, string>, boolean][]] {
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
  const conditional: [string, Function, Record<string, string>, boolean][] = [];
  const branches = builder.branches;
  if (branches && typeof branches === "object") {
    for (const [srcNode, branchMap] of Object.entries(branches as Record<string, unknown>)) {
      if (typeof branchMap !== "object" || branchMap === null) continue;
      for (const [, branchSpec] of Object.entries(branchMap as Record<string, unknown>)) {
        if (typeof branchSpec !== "object" || branchSpec === null) continue;
        const spec = branchSpec as Record<string, unknown>;
        const path = spec.path as Record<string, unknown> | undefined;
        if (!path) continue;
        const routerFunc = path.func;
        if (typeof routerFunc !== "function") continue;
        const targets = spec.ends;
        if (!targets || typeof targets !== "object") continue;
        const isDynamic = _isSendRouter(routerFunc as Function);
        conditional.push([
          srcNode,
          routerFunc as Function,
          targets as Record<string, string>,
          isDynamic,
        ]);
      }
    }
  }

  return [edges, conditional];
}

// ── Human node detection ────────────────────────────────

function _isHumanNode(func: Function): boolean {
  return (func as any)._agentspan_human_task === true;
}

// ── LLM node detection ──────────────────────────────────

/**
 * Find an LLM object referenced by a node function.
 *
 * In JS, closures are sealed — we can't access module-level variables like
 * Python's func.__globals__. Instead, we use two strategies:
 * 1. Check function source for .invoke() patterns
 * 2. Search the graph's node tree for LLM-like objects (with model_name + invoke)
 *
 * Returns { llm, path } or null.
 */
function _findLLMInNode(
  func: Function,
  graph: unknown,
  llmObjHint?: unknown,
): { llm: unknown; path: string } | null {
  // Quick check: does the function source reference .invoke()?
  const funcSource = func.toString();
  const hasInvokeCall = funcSource.includes(".invoke(") || funcSource.includes(".invoke (");
  if (!hasInvokeCall) return null;

  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || typeof nodes !== "object") return null;

  // Search all graph nodes for LLM-like objects
  const seen = new WeakSet<object>();
  const entries: [string, unknown][] =
    nodes instanceof Map
      ? Array.from((nodes as Map<string, unknown>).entries())
      : Object.entries(nodes);

  for (const [, node] of entries) {
    const result = _searchForLLM(node, 6, seen);
    if (result) return result;
  }

  // Search graph-level properties
  for (const key of Object.keys(g)) {
    if (key.startsWith("_") || key === "nodes" || key === "builder") continue;
    const val = g[key];
    if (val && typeof val === "object") {
      const result = _searchForLLM(val, 4, seen);
      if (result) return result;
    }
  }

  // Even if we can't find the LLM object, we can detect LLM calls
  // from the function source. JS closures are sealed — module-level LLM
  // objects aren't reachable via the graph tree.
  if (_looksLikeLLMCall(funcSource) || _findModelInGraph(graph) != null) {
    // If the caller provided an LLM object hint (from run()/deploy() options
    // or _agentspan.llm metadata), use it for monkey-patching. Otherwise
    // fall back to null which triggers client-side passthrough.
    return { llm: llmObjHint ?? null, path: llmObjHint ? "__option__" : "__inferred__" };
  }

  return null;
}

/**
 * Heuristic check: does function source look like an LLM call?
 * Checks for message construction patterns (LangChain messages, OpenAI-style dicts)
 * combined with .invoke() — strong evidence of an LLM call vs other Runnable.invoke().
 */
function _looksLikeLLMCall(source: string): boolean {
  // LangChain message construction patterns
  if (source.includes("Message")) {
    if (
      source.includes("System") ||
      source.includes("Human") ||
      source.includes("AI") ||
      source.includes("Chat")
    ) {
      return true;
    }
  }
  // OpenAI-style dict messages: { role: "system", content: ... }
  if (source.includes("role") && source.includes("content") && source.includes("system")) {
    return true;
  }
  // Common LLM variable names before .invoke
  for (const varName of [
    "llm.invoke",
    "model.invoke",
    "chat.invoke",
    "chatModel.invoke",
    "chatLLM.invoke",
    "llm.call",
    "model.call",
    "llm.generate",
    "model.generate",
    "llm.stream",
    "model.stream",
    "chat.stream",
  ]) {
    if (source.includes(varName)) return true;
  }
  // .invoke() + response.content pattern — strong LLM signal
  if (source.includes(".invoke(") && source.includes(".content")) {
    return true;
  }
  // Template literal or string concat with prompt-like patterns
  if (source.includes(".invoke(") && (source.includes("prompt") || source.includes("Prompt"))) {
    return true;
  }
  return false;
}

/**
 * Recursively search for an LLM-like object in obj.
 * Returns { llm, path } or null.
 */
function _searchForLLM(
  obj: unknown,
  depth: number,
  seen: WeakSet<object>,
): { llm: unknown; path: string } | null {
  if (depth <= 0 || obj == null || typeof obj !== "object") return null;
  if (seen.has(obj as object)) return null;
  seen.add(obj as object);

  // Check if this object IS an LLM
  const modelStr = _tryGetModelString(obj);
  if (modelStr && typeof (obj as any).invoke === "function") {
    // It has a model string and an invoke method — it's an LLM
    const clsName = (obj as any).constructor?.name ?? "llm";
    return { llm: obj, path: clsName };
  }

  const asAny = obj as Record<string, unknown>;

  // Walk common nested property names
  for (const attr of ["bound", "first", "last", "runnable", "func", "llm", "model"]) {
    const child = asAny[attr];
    if (child != null && child !== obj && typeof child === "object") {
      const found = _searchForLLM(child, depth - 1, seen);
      if (found) return found;
    }
  }

  // Walk middle array
  if (Array.isArray(asAny.middle)) {
    for (const child of asAny.middle) {
      const found = _searchForLLM(child, depth - 1, seen);
      if (found) return found;
    }
  }

  return null;
}

// ── Subgraph detection ──────────────────────────────────

function _isCompiledGraph(obj: unknown): boolean {
  if (typeof obj !== "object" || obj === null) return false;
  // Use LangGraph's own marker property — most reliable check.
  // CompiledStateGraph, CompiledGraph, and Pregel all set lg_is_pregel = true.
  // This avoids false positives from PregelNode (which also contains "Pregel").
  if ((obj as any).lg_is_pregel === true) return true;
  // Fallback: exact class name check (excludes PregelNode, PregelTaskDescription, etc.)
  const typeName = (obj as any).constructor?.name ?? "";
  return (
    typeName.includes("CompiledStateGraph") ||
    typeName.includes("CompiledGraph") ||
    typeName === "Pregel"
  );
}

/**
 * Walk the prototype chain of a compiled graph to find the prototype
 * that owns `.invoke()`. This is the Pregel prototype shared by ALL
 * compiled graphs — patching it intercepts invoke on every instance.
 */
function _getPregelPrototype(graph: unknown): { proto: any; origInvoke: Function } | null {
  if (typeof graph !== "object" || graph === null) return null;
  let proto = Object.getPrototypeOf(graph);
  while (proto != null) {
    if (Object.hasOwn(proto, "invoke") && typeof proto.invoke === "function") {
      return { proto, origInvoke: proto.invoke };
    }
    proto = Object.getPrototypeOf(proto);
  }
  return null;
}

/**
 * Detect a subgraph by temporarily patching Pregel.prototype.invoke
 * and running the node function. When the function calls ANY compiled
 * graph's .invoke(), our patch captures `this` (the subgraph object)
 * via a thrown _CapturedSubgraphCall.
 *
 * This handles the common pattern where a subgraph is captured via
 * a JS closure (unreachable from outside), which the graph-tree search
 * cannot find. Python uses bytecode introspection (co_names + __globals__)
 * for this; in JS we use runtime interception instead.
 */
function _findSubgraphViaRuntime(
  func: Function,
  graph: unknown,
): { subgraph: unknown; path: string } | null {
  const pregel = _getPregelPrototype(graph);
  if (!pregel) return null;

  let captured: unknown = null;

  // Temporarily patch the shared Pregel prototype invoke
  pregel.proto.invoke = function (this: unknown, input: unknown) {
    // eslint-disable-next-line @typescript-eslint/no-this-alias -- intentional: capturing call-site receiver
    captured = this;
    throw new _CapturedSubgraphCall(input);
  };

  // Build a proxy state that returns safe defaults for any property access,
  // so the function doesn't crash before reaching .invoke()
  const proxyState = new Proxy({} as Record<string, unknown>, {
    get(_target, prop) {
      if (prop === Symbol.toPrimitive) return () => "";
      if (prop === Symbol.iterator) return undefined;
      if (typeof prop === "symbol") return undefined;
      // Return an empty string for common state fields; the function
      // only needs to reach the .invoke() call, not produce valid output.
      return "";
    },
  });

  try {
    // Run the function. For async functions, the patched invoke throws
    // synchronously before the first await, setting `captured` before
    // the throw propagates. The throw becomes a rejected promise which
    // we must suppress to avoid crashing the process.
    const maybePromise = (func as any)(proxyState);
    if (maybePromise && typeof maybePromise.then === "function") {
      maybePromise.catch(() => {}); // suppress unhandled rejection
    }
  } catch {
    // Expected: _CapturedSubgraphCall or state access error (sync path)
  } finally {
    pregel.proto.invoke = pregel.origInvoke;
  }

  if (captured != null && captured !== graph && _isCompiledGraph(captured)) {
    const clsName = (captured as any).constructor?.name ?? "subgraph";
    _debugLog?.("_findSubgraphViaRuntime: captured", clsName);
    return { subgraph: captured, path: clsName };
  }

  return null;
}

/**
 * Find a compiled subgraph referenced by a node function.
 *
 * Uses a layered detection strategy:
 * 1. LangGraph's built-in getSubgraphs() API — catches direct subgraph nodes
 * 2. Graph-tree search — walks node wrapper objects for embedded subgraphs
 * 3. Runtime detection — patches Pregel.prototype.invoke and runs the function
 *    to capture closure-held subgraphs (the JS equivalent of Python's
 *    co_names + __globals__ bytecode introspection)
 *
 * Returns { subgraph, path } or null.
 */
function _findSubgraphInNode(
  func: Function,
  graph: unknown,
  nodeName?: string,
): { subgraph: unknown; path: string } | null {
  const g = graph as Record<string, unknown>;

  // Quick check: does the function source contain .invoke() at all?
  const funcSource = func.toString();
  const hasInvoke = funcSource.includes(".invoke(") || funcSource.includes(".invoke (");
  if (!hasInvoke) return null;

  // Strategy 1: LangGraph's built-in getSubgraphs() API
  // Works when a compiled graph is passed directly to addNode()
  if (nodeName && typeof (g as any).getSubgraphs === "function") {
    try {
      for (const [name, sg] of (g as any).getSubgraphs()) {
        if (name === nodeName && _isCompiledGraph(sg)) {
          _debugLog?.("_findSubgraphInNode: found via getSubgraphs() for", nodeName);
          return { subgraph: sg, path: name };
        }
      }
    } catch {
      /* getSubgraphs() not available or failed */
    }
  }

  // Strategy 2: Graph-tree search — walk node wrappers for embedded subgraphs
  const nodes = g.nodes;
  if (nodes && typeof nodes === "object") {
    const seen = new WeakSet<object>();
    const entries: [string, unknown][] =
      nodes instanceof Map
        ? Array.from((nodes as Map<string, unknown>).entries())
        : Object.entries(nodes);

    for (const [, node] of entries) {
      const result = _searchForSubgraph(node, 5, seen, graph);
      if (result) {
        _debugLog?.("_findSubgraphInNode: found via graph-tree search");
        return result;
      }
    }
  }

  // Strategy 3: Runtime detection via Pregel prototype patching
  // This catches subgraphs captured via JS closures (opaque from outside).
  // Skip if the function looks like an LLM call — avoid false positive.
  if (!_looksLikeLLMCall(funcSource)) {
    const runtimeResult = _findSubgraphViaRuntime(func, graph);
    if (runtimeResult) return runtimeResult;
  }

  return null;
}

function _searchForSubgraph(
  obj: unknown,
  depth: number,
  seen: WeakSet<object>,
  parentGraph: unknown,
): { subgraph: unknown; path: string } | null {
  if (depth <= 0 || obj == null || typeof obj !== "object") return null;
  if (seen.has(obj as object)) return null;
  seen.add(obj as object);

  // Check if this is a compiled graph (but NOT the parent graph itself)
  if (obj !== parentGraph && _isCompiledGraph(obj)) {
    const clsName = (obj as any).constructor?.name ?? "subgraph";
    return { subgraph: obj, path: clsName };
  }

  const asAny = obj as Record<string, unknown>;
  for (const attr of ["bound", "first", "last", "runnable", "func"]) {
    const child = asAny[attr];
    if (child != null && child !== obj && typeof child === "object") {
      const found = _searchForSubgraph(child, depth - 1, seen, parentGraph);
      if (found) return found;
    }
  }

  return null;
}

// ── Dynamic fanout (Send API) detection ─────────────────

function _isSendRouter(func: Function): boolean {
  const src = func.toString();
  return src.includes("Send");
}

// ── Input key extraction ────────────────────────────────

function _extractInputKey(graph: unknown): string | null {
  try {
    const g = graph as any;

    // Method 1: getInputJsonSchema (if available)
    if (typeof g.getInputJsonSchema === "function") {
      const schema = g.getInputJsonSchema();
      if (schema?.properties) {
        const required: string[] = schema.required || Object.keys(schema.properties);
        for (const field of required) {
          const prop = schema.properties[field];
          if (prop?.type === "string") return field;
        }
        const keys = Object.keys(schema.properties);
        if (keys.length > 0) return keys[0];
      }
    }

    // Method 2: Examine channels — find first string-default channel
    const channels = g.channels;
    if (channels && typeof channels === "object") {
      const entries: [string, unknown][] =
        channels instanceof Map ? Array.from(channels.entries()) : Object.entries(channels);

      for (const [chName, chObj] of entries) {
        if (chName.startsWith("__") || chName.startsWith("branch:")) continue;
        const ch = chObj as any;
        // BinaryOperatorAggregate has a .value or default() that reveals the type
        const defaultVal =
          ch.value ?? (typeof ch.default === "function" ? ch.default() : ch.default);
        if (typeof defaultVal === "string") return chName;
      }
    }

    return null;
  } catch {
    return null;
  }
}

// ── Reducer extraction ──────────────────────────────────

function _extractReducers(graph: unknown): Record<string, string> | null {
  try {
    const channels = (graph as any).channels;
    if (!channels || typeof channels !== "object") return null;

    const reducers: Record<string, string> = {};
    const entries: [string, unknown][] =
      channels instanceof Map ? Array.from(channels.entries()) : Object.entries(channels);

    for (const [chName, chObj] of entries) {
      if (chName.startsWith("__") || chName.startsWith("branch:")) continue;
      const typeName = (chObj as any)?.constructor?.name ?? "";
      if (typeName === "BinaryOperatorAggregate") {
        const op = (chObj as any).operator;
        if (op != null) {
          reducers[chName] = _inferReducerType(op);
        }
      }
    }

    return Object.keys(reducers).length > 0 ? reducers : null;
  } catch {
    return null;
  }
}

// ── Retry policy extraction ─────────────────────────────

function _extractRetryPolicies(graph: unknown): Record<string, Record<string, unknown>> | null {
  try {
    const builder = (graph as any).builder;
    if (!builder?._nodes) return null;

    const policies: Record<string, Record<string, unknown>> = {};
    for (const [nodeName, nodeSpec] of Object.entries(builder._nodes as Record<string, any>)) {
      const retry = nodeSpec?.retry;
      if (!retry) continue;
      const policy: Record<string, unknown> = {};
      if (retry.maxAttempts != null || retry.max_attempts != null) {
        policy.max_attempts = retry.maxAttempts ?? retry.max_attempts;
      }
      if (retry.initialInterval != null || retry.initial_interval != null) {
        policy.initial_interval = retry.initialInterval ?? retry.initial_interval;
      }
      if (retry.backoffFactor != null || retry.backoff_factor != null) {
        policy.backoff_factor = retry.backoffFactor ?? retry.backoff_factor;
      }
      if (retry.maxInterval != null || retry.max_interval != null) {
        policy.max_interval = retry.maxInterval ?? retry.max_interval;
      }
      if (Object.keys(policy).length > 0) {
        policies[nodeName] = policy;
      }
    }

    return Object.keys(policies).length > 0 ? policies : null;
  } catch {
    return null;
  }
}

// ── Reducer type inference ───────────────────────────────

/**
 * Infer a reducer type from the operator function source.
 * Matches Python's operator names (add, replace, etc.).
 */
function _inferReducerType(op: Function): string {
  const src = op.toString();
  // Replace patterns: (a, b) => b ?? a, (_, n) => n, (p, n) => n ?? p
  if (src.includes("??") || /=>\s*\w+\s*$/.test(src.trim())) return "replace";
  // Array spread/concat: [...a, ...b] or a.concat(b)
  if (src.includes("...") && src.includes("[")) return "add";
  if (src.includes(".concat(")) return "add";
  // Numeric addition: a + b
  if (/\w\s*\+\s*\w/.test(src) && !src.includes('"') && !src.includes("'") && !src.includes("`"))
    return "add";
  // Named function (if not the generic "reducer" from Annotation)
  const name = op.name;
  if (name && name !== "reducer" && name !== "anonymous" && name !== "") return name;
  return "replace";
}

// ── LLM interception workers ────────────────────────────

class _CapturedLLMCall extends Error {
  constructor(public messages: unknown[]) {
    super("LLM call captured");
  }
}

/**
 * Resolve LangChain chat model classes for prototype patching.
 *
 * LangChain's class hierarchy has multiple levels that override `invoke`:
 *   ChatOpenAI → BaseChatOpenAI (has invoke) → BaseChatModel (has invoke) → ...
 *
 * We need to patch ALL prototypes that define `invoke` so the closest one
 * in the chain is intercepted. We collect classes from @langchain/core and
 * known provider packages.
 */
let _chatModelClasses: any[] | undefined; // undefined = not yet tried
async function _getChatModelClasses(): Promise<any[]> {
  if (_chatModelClasses !== undefined) return _chatModelClasses;
  const classes: any[] = [];

  // Core: BaseChatModel
  try {
    const mod = await import("@langchain/core/language_models/chat_models");
    if (mod.BaseChatModel) classes.push(mod.BaseChatModel);
  } catch (e) {
    _debugLog?.("import @langchain/core failed:", e);
  }

  // Provider packages — each may add intermediate classes with their own invoke
  const providerImports = [
    ["@langchain/openai", ["ChatOpenAI", "BaseChatOpenAI"]],
    ["@langchain/anthropic", ["ChatAnthropic"]],
    ["@langchain/google-genai", ["ChatGoogleGenerativeAI"]],
    ["@langchain/google-vertexai", ["ChatVertexAI"]],
    ["@langchain/community/chat_models/bedrock", ["BedrockChat"]],
  ] as const;

  for (const [pkg, classNames] of providerImports) {
    try {
      const mod = await import(pkg);
      for (const name of classNames) {
        if (mod[name]) classes.push(mod[name]);
      }
    } catch (e) {
      _debugLog?.("import", pkg, "failed:", e);
    }
  }

  _debugLog?.("_getChatModelClasses found", classes.length, "classes");
  _chatModelClasses = classes;
  return classes;
}

/**
 * Patch `invoke` on all prototypes in LangChain's chat model hierarchy.
 * Returns a restore function that undoes all patches.
 */
async function _patchAllInvokes(replacement: Function): Promise<(() => void) | null> {
  const classes = await _getChatModelClasses();
  if (classes.length === 0) return null;

  const patches: { proto: any; original: Function }[] = [];
  const seen = new WeakSet();

  for (const cls of classes) {
    // Walk up this class's prototype chain, patching every `invoke` we find
    let proto = cls.prototype;
    while (proto && !seen.has(proto)) {
      seen.add(proto);
      if (Object.hasOwn(proto, "invoke")) {
        patches.push({ proto, original: proto.invoke });
        proto.invoke = replacement;
      }
      proto = Object.getPrototypeOf(proto);
    }
  }

  _debugLog?.("_patchAllInvokes: patched", patches.length, "prototypes");
  if (patches.length === 0) return null;
  return () => {
    for (const { proto, original } of patches) {
      proto.invoke = original;
    }
  };
}

/**
 * Known LLM API endpoint patterns for fetch interception.
 */
const _LLM_ENDPOINT_PATTERNS = [
  /api\.openai\.com\/v1\/chat\/completions/,
  /api\.anthropic\.com\/v1\/messages/,
  /generativelanguage\.googleapis\.com/,
  /api\.groq\.com\/openai\/v1\/chat\/completions/,
  /api\.together\.xyz/,
  /api\.fireworks\.ai/,
  /api\.mistral\.ai/,
  /bedrock-runtime\..+\.amazonaws\.com/,
  /\/v1\/chat\/completions/, // Generic OpenAI-compatible endpoints
];

function _isLLMEndpoint(url: string): boolean {
  return _LLM_ENDPOINT_PATTERNS.some((p) => p.test(url));
}

/**
 * Build a fake OpenAI-compatible response to satisfy SDK response parsing.
 */
function _fakeLLMResponse(content: string): Response {
  const body = JSON.stringify({
    id: "agentspan-capture",
    object: "chat.completion",
    choices: [
      {
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop",
      },
    ],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  });
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Persistent fetch interceptor state.
 *
 * Some LLM SDKs (e.g., openai v6+) cache the `fetch` reference after their
 * first call. Overriding globalThis.fetch and restoring it between calls doesn't
 * work because the SDK keeps using the cached reference. Instead, we install ONE
 * persistent interceptor and control its behavior via this state object.
 */
interface _FetchInterceptState {
  mode: "passthrough" | "capture" | "mock";
  capturedMessages: unknown[] | null;
  mockContent: string;
}

const _fetchState: _FetchInterceptState = {
  mode: "passthrough",
  capturedMessages: null,
  mockContent: "",
};

let _fetchInterceptorInstalled = false;
let _origFetch: typeof globalThis.fetch | null = null;

function _ensureFetchInterceptor(): void {
  if (_fetchInterceptorInstalled) return;
  _origFetch = globalThis.fetch;
  _fetchInterceptorInstalled = true;

  globalThis.fetch = async function (
    input: string | URL | Request,
    init?: RequestInit,
  ): Promise<Response> {
    if (_fetchState.mode === "passthrough") {
      return _origFetch!.call(globalThis, input, init);
    }

    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : (input as Request).url;

    if (_isLLMEndpoint(url)) {
      if (_fetchState.mode === "capture" && init?.body && !_fetchState.capturedMessages) {
        try {
          const bodyStr = typeof init.body === "string" ? init.body : String(init.body);
          const body = JSON.parse(bodyStr);
          if (Array.isArray(body.messages)) {
            _fetchState.capturedMessages = body.messages;
            return _fakeLLMResponse("");
          }
        } catch {
          /* not JSON — pass through */
        }
      }
      if (_fetchState.mode === "mock") {
        return _fakeLLMResponse(_fetchState.mockContent);
      }
    }

    return _origFetch!.call(globalThis, input, init);
  };
}

/**
 * Intercept LLM invoke calls and capture messages.
 *
 * Three strategies (tried in combination):
 * 1. Direct instance patch — if we have the LLM object, patch .invoke() directly
 * 2. Prototype chain patch — patch BaseChatModel.prototype.invoke() etc.
 * 3. Fetch interception — intercept globalThis.fetch for LLM API endpoints
 *
 * Strategies 2 and 3 run simultaneously as belt-and-suspenders. Strategy 2
 * may fail when the SDK and user code resolve LangChain from different
 * node_modules (e.g., in workspace setups with duplicate dependencies).
 * Strategy 3 uses a persistent globalThis.fetch interceptor that's immune
 * to both module duplication and SDK fetch caching.
 *
 * Python equivalent: node_func.__globals__[llm_var_name] = _LLMCaptureProxy()
 */
async function _withCaptureInvoke(
  llmObj: unknown,
  fn: () => Promise<unknown>,
): Promise<{ captured: true; messages: unknown[] } | { captured: false; result: unknown }> {
  // Strategy 1: direct instance patch (most reliable when LLM object is available)
  if (llmObj) {
    const llm = llmObj as any;
    const origInvoke = llm.invoke;
    const origCall = typeof llm.__call__ === "function" ? llm.__call__ : undefined;
    llm.invoke = async (msgs: unknown[]) => {
      throw new _CapturedLLMCall(Array.isArray(msgs) ? msgs : [msgs]);
    };
    if (origCall !== undefined) llm.__call__ = llm.invoke;
    try {
      const result = await Promise.resolve(fn());
      return { captured: false, result };
    } catch (e) {
      if (e instanceof _CapturedLLMCall) return { captured: true, messages: e.messages };
      throw e;
    } finally {
      llm.invoke = origInvoke;
      if (origCall !== undefined) llm.__call__ = origCall;
    }
  }

  // Strategies 2+3: prototype patch + fetch interception (for closure-captured LLMs)

  // Strategy 3: persistent fetch interceptor in capture mode
  _ensureFetchInterceptor();
  _fetchState.mode = "capture";
  _fetchState.capturedMessages = null;

  // Strategy 2: prototype chain patch (may work if modules are deduplicated)
  const captureInvoke = async function captureInvoke(this: any, msgs: unknown[]) {
    throw new _CapturedLLMCall(Array.isArray(msgs) ? msgs : [msgs]);
  };
  const restore = await _patchAllInvokes(captureInvoke);

  try {
    const result = await Promise.resolve(fn());

    // Function completed without prototype-patch throwing.
    // Check if fetch interception captured messages.
    if (_fetchState.capturedMessages) {
      return { captured: true, messages: _fetchState.capturedMessages };
    }

    return { captured: false, result };
  } catch (e) {
    if (e instanceof _CapturedLLMCall) return { captured: true, messages: e.messages };
    throw e;
  } finally {
    _fetchState.mode = "passthrough";
    _fetchState.capturedMessages = null;
    if (restore) restore();
  }
}

/**
 * Re-run a node function with a mock LLM that returns the server's response.
 * Mirrors _withCaptureInvoke's three-strategy approach.
 */
async function _withMockInvoke(
  llmObj: unknown,
  llmResult: string,
  fn: () => Promise<unknown>,
): Promise<unknown> {
  const mockInvoke = async () => ({ content: llmResult, tool_calls: [], type: "ai" });

  // Strategy 1: direct instance patch
  if (llmObj) {
    const llm = llmObj as any;
    const origInvoke = llm.invoke;
    const origCall = typeof llm.__call__ === "function" ? llm.__call__ : undefined;
    llm.invoke = mockInvoke;
    if (origCall !== undefined) llm.__call__ = mockInvoke;
    try {
      return await Promise.resolve(fn());
    } finally {
      llm.invoke = origInvoke;
      if (origCall !== undefined) llm.__call__ = origCall;
    }
  }

  // Strategies 2+3: prototype patch + fetch interception

  // Strategy 3: persistent fetch interceptor in mock mode
  _ensureFetchInterceptor();
  _fetchState.mode = "mock";
  _fetchState.mockContent = llmResult;

  // Strategy 2: prototype chain patch
  const restore = await _patchAllInvokes(mockInvoke);

  try {
    return await Promise.resolve(fn());
  } finally {
    _fetchState.mode = "passthrough";
    _fetchState.mockContent = "";
    if (restore) restore();
  }
}

/**
 * Build a prep worker that intercepts llm.invoke() and captures messages.
 *
 * Workers receive raw inputData from the polling loop (not a task wrapper).
 * They return output directly — the worker manager wraps it in status/outputData.
 */
function makeLLMPrepWorker(nodeFunc: Function, nodeName: string, llmObj: unknown): Function {
  return async (inputData: Record<string, unknown>) => {
    const state = (inputData.state as Record<string, unknown>) || {};

    const outcome = await _withCaptureInvoke(llmObj, () => (nodeFunc as any)(state));

    if (outcome.captured) {
      const serialized = _serializeMessages(outcome.messages);
      return { messages: serialized, state };
    }

    // Function completed without calling llm.invoke() — passthrough
    const update = outcome.result;
    const merged = { ...state, ...(update && typeof update === "object" ? update : {}) };
    return { messages: [], state: merged, result: _stateToResult(merged), _skip_llm: true };
  };
}

/**
 * Build a finish worker that re-runs the node with a mock LLM response.
 */
function makeLLMFinishWorker(nodeFunc: Function, nodeName: string, llmObj: unknown): Function {
  return async (inputData: Record<string, unknown>) => {
    const state = (inputData.state as Record<string, unknown>) || {};
    const llmResult = (inputData.llm_result as string) || "";

    const update = await _withMockInvoke(llmObj, llmResult, () => (nodeFunc as any)(state));
    const merged = { ...state, ...(update && typeof update === "object" ? update : {}) };
    return { state: merged, result: _stateToResult(merged) };
  };
}

// ── Subgraph interception workers ───────────────────────

class _CapturedSubgraphCall extends Error {
  constructor(public inputData: unknown) {
    super("Subgraph call captured");
  }
}

function makeSubgraphPrepWorker(
  nodeFunc: Function,
  nodeName: string,
  subgraphObj: unknown,
): Function {
  return async (inputData: Record<string, unknown>) => {
    const state = (inputData.state as Record<string, unknown>) || {};

    const sg = subgraphObj as any;
    const originalInvoke = sg.invoke;

    sg.invoke = async (input: unknown) => {
      throw new _CapturedSubgraphCall(input);
    };

    try {
      const update = await Promise.resolve((nodeFunc as any)(state));
      const merged = { ...state, ...(update && typeof update === "object" ? update : {}) };
      return {
        subgraph_input: {},
        state: merged,
        result: _stateToResult(merged),
        _skip_subgraph: true,
      };
    } catch (e) {
      if (e instanceof _CapturedSubgraphCall) {
        return { subgraph_input: e.inputData, state };
      }
      throw e;
    } finally {
      sg.invoke = originalInvoke;
    }
  };
}

function makeSubgraphFinishWorker(
  nodeFunc: Function,
  nodeName: string,
  subgraphObj: unknown,
): Function {
  return async (inputData: Record<string, unknown>) => {
    const state = (inputData.state as Record<string, unknown>) || {};
    const subgraphResult = inputData.subgraph_result || {};

    const sg = subgraphObj as any;
    const originalInvoke = sg.invoke;

    sg.invoke = async () => subgraphResult;

    try {
      const update = await Promise.resolve((nodeFunc as any)(state));
      const merged = { ...state, ...(update && typeof update === "object" ? update : {}) };
      return { state: merged, result: _stateToResult(merged) };
    } finally {
      sg.invoke = originalInvoke;
    }
  };
}

// ── Regular node worker ─────────────────────────────────

function makeNodeWorker(nodeFunc: Function, _nodeName: string): Function {
  return async (inputData: Record<string, unknown>) => {
    const state = (inputData.state as Record<string, unknown>) || {};
    const update = await Promise.resolve((nodeFunc as any)(state));
    const merged = { ...state, ...(update && typeof update === "object" ? update : {}) };
    return { state: merged, result: _stateToResult(merged) };
  };
}

// ── Router worker ───────────────────────────────────────

function makeRouterWorker(
  routerFunc: Function,
  routerName: string,
  isDynamicFanout: boolean,
): Function {
  return async (inputData: Record<string, unknown>) => {
    const state = (inputData.state as Record<string, unknown>) || {};
    const decision = await Promise.resolve((routerFunc as any)(state));

    if (isDynamicFanout && Array.isArray(decision)) {
      const dynamicTasks = decision.map((item: any) => ({
        node: item.node ?? item.name,
        input: item.arg ?? item.args ?? item.input ?? item,
      }));
      return { dynamic_tasks: dynamicTasks, state };
    }

    return { decision: String(decision), state };
  };
}

// ── Message serialization ───────────────────────────────

function _serializeMessages(messages: unknown[]): Array<Record<string, string>> {
  const result: Array<Record<string, string>> = [];
  if (!Array.isArray(messages)) return result;

  for (const msg of messages) {
    const role = _langchainRole(msg);
    let content: string;
    if (typeof msg === "object" && msg !== null) {
      const m = msg as any;
      content = m.content ?? m.text ?? String(msg);
    } else {
      content = String(msg);
    }
    result.push({ role, message: String(content) });
  }
  return result;
}

function _langchainRole(msg: unknown): string {
  if (typeof msg !== "object" || msg === null) return "user";
  const m = msg as any;

  // LangChain message type detection
  const typeName = m.constructor?.name ?? "";
  if (typeName.includes("System")) return "system";
  if (typeName.includes("Human") || typeName.includes("User")) return "user";
  if (typeName.includes("AI") || typeName.includes("Assistant")) return "assistant";

  // _getType method (LangChain JS)
  if (typeof m._getType === "function") {
    const t = m._getType();
    if (t === "system") return "system";
    if (t === "human") return "user";
    if (t === "ai") return "assistant";
  }

  // Dict-style messages
  if (typeof m.role === "string") {
    if (m.role === "human") return "user";
    if (m.role === "ai") return "assistant";
    return m.role;
  }

  return "user";
}

// ── State helpers ───────────────────────────────────────

function _stateToResult(state: Record<string, unknown>): string {
  for (const key of ["result", "final_email", "output", "answer", "response"]) {
    if (state[key]) return String(state[key]);
  }
  try {
    return JSON.stringify(state);
  } catch {
    return String(state);
  }
}

// ── Model from explicit option ──────────────────────────

/**
 * Extract model string from an explicit option passed via run()/deploy().
 * Accepts a string ('openai/gpt-4o-mini') or an LLM object (ChatOpenAI instance).
 */
function _extractModelFromOption(model: unknown): string | null {
  if (typeof model === "string" && model.length > 0) {
    if (model.includes("/")) return model;
    const provider = _inferProvider("", model);
    return provider ? `${provider}/${model}` : model;
  }
  if (typeof model !== "object" || model === null) return null;

  const obj = model as Record<string, unknown>;
  const modelName =
    (typeof obj.model === "string" && obj.model) ||
    (typeof obj.modelName === "string" && obj.modelName) ||
    (typeof obj.model_name === "string" && obj.model_name) ||
    (typeof obj.modelId === "string" && obj.modelId) ||
    null;

  if (!modelName || modelName.length > 100) return null;
  if (modelName.includes("/")) return modelName;

  const clsName = model.constructor?.name ?? "";
  const provider = _inferProvider(clsName, modelName);
  return provider ? `${provider}/${modelName}` : modelName;
}

// ── Model finding ───────────────────────────────────────

function _findModelInGraph(graph: unknown): string | null {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || typeof nodes !== "object") return null;

  const values: unknown[] =
    nodes instanceof Map
      ? Array.from((nodes as Map<string, unknown>).values())
      : Object.values(nodes);

  for (const node of values) {
    const model = _searchForModel(node, 5);
    if (model) return model;
  }

  return null;
}

function _searchForModel(obj: unknown, depth: number): string | null {
  if (depth <= 0) return null;
  const result = _tryGetModelString(obj);
  if (result) return result;

  if (typeof obj !== "object" || obj === null) return null;
  const asAny = obj as Record<string, unknown>;

  for (const attr of ["bound", "first", "last", "runnable", "func"]) {
    const child = asAny[attr];
    if (child != null && child !== obj) {
      const found = _searchForModel(child, depth - 1);
      if (found) return found;
    }
  }

  const middle = asAny.middle;
  if (Array.isArray(middle)) {
    for (const child of middle) {
      const found = _searchForModel(child, depth - 1);
      if (found) return found;
    }
  }

  const steps = asAny.steps;
  if (steps && typeof steps === "object" && !Array.isArray(steps)) {
    for (const child of Object.values(steps as Record<string, unknown>)) {
      const found = _searchForModel(child, depth - 1);
      if (found) return found;
    }
  }

  return null;
}

function _tryGetModelString(obj: unknown): string | null {
  if (typeof obj !== "object" || obj === null) return null;
  const asAny = obj as Record<string, unknown>;
  const clsName = (obj as any).constructor?.name ?? "";

  const modelName =
    (typeof asAny.model_name === "string" && asAny.model_name) ||
    (typeof asAny.modelName === "string" && asAny.modelName) ||
    (typeof asAny.model === "string" && asAny.model) ||
    null;

  if (!modelName || modelName.length > 100) return null;
  if (modelName.startsWith("<") || modelName.startsWith("(")) return null;

  if (modelName.includes("/")) return modelName;

  const provider = _inferProvider(clsName, modelName);
  return provider ? `${provider}/${modelName}` : modelName;
}

function _inferProvider(clsName: string, modelName: string): string | null {
  if (clsName.includes("OpenAI") || clsName.includes("openai")) return "openai";
  if (clsName.includes("Anthropic") || clsName.includes("anthropic")) return "anthropic";
  if (clsName.includes("Google") || clsName.includes("google")) return "google";
  if (clsName.includes("Bedrock")) return "bedrock";
  if (
    modelName.startsWith("gpt-") ||
    modelName.startsWith("o1") ||
    modelName.startsWith("o3") ||
    modelName.startsWith("o4")
  )
    return "openai";
  if (modelName.includes("claude")) return "anthropic";
  if (modelName.includes("gemini")) return "google";
  return null;
}

// ── Tool finding ────────────────────────────────────────

function _findToolsInGraph(graph: unknown): unknown[] {
  const g = graph as Record<string, unknown>;
  const nodes = g.nodes;
  if (!nodes || typeof nodes !== "object") return [];

  const values: unknown[] =
    nodes instanceof Map
      ? Array.from((nodes as Map<string, unknown>).values())
      : Object.values(nodes);

  for (const node of values) {
    const tools = _searchForTools(node, 3);
    if (tools.length > 0) return tools;
  }
  return [];
}

function _searchForTools(obj: unknown, depth: number): unknown[] {
  if (depth <= 0) return [];
  if (typeof obj !== "object" || obj === null) return [];
  const asAny = obj as Record<string, unknown>;

  // Check tools_by_name dict (Python LangGraph ToolNode pattern)
  const toolsByName = asAny.tools_by_name;
  if (toolsByName && typeof toolsByName === "object") {
    if (toolsByName instanceof Map) {
      return Array.from(toolsByName.values());
    }
    if (!Array.isArray(toolsByName)) {
      return Object.values(toolsByName as Record<string, unknown>);
    }
  }

  // Check tools array (JS LangGraph ToolNode pattern — bound.tools is an array)
  const toolsArr = asAny.tools;
  if (Array.isArray(toolsArr) && toolsArr.length > 0) {
    // Validate that these look like tool objects (have name + description)
    const first = toolsArr[0] as Record<string, unknown> | null;
    if (first && typeof first === "object" && typeof first.name === "string") {
      return toolsArr;
    }
  }

  for (const attr of ["bound", "runnable", "func"]) {
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
  if (!nodes || typeof nodes !== "object") return null;

  const entries: [string, unknown][] =
    nodes instanceof Map
      ? Array.from((nodes as Map<string, unknown>).entries())
      : Object.entries(nodes);

  for (const [nodeName, node] of entries) {
    if (nodeName === "__start__" || nodeName === "__end__") continue;
    if (typeof node !== "object" || node === null) continue;
    const n = node as Record<string, unknown>;

    const config = n.config as Record<string, unknown> | undefined;
    if (config) {
      const prompt = config.system_prompt ?? config.system_message ?? config.systemPrompt;
      if (typeof prompt === "string") return prompt;
    }
  }

  return null;
}

// ── Tool schema/callable extraction ─────────────────────

function _getToolSchema(toolObj: unknown): Record<string, unknown> {
  if (typeof toolObj !== "object" || toolObj === null) {
    return { type: "object", properties: {} };
  }
  const t = toolObj as Record<string, unknown>;

  if (t.args_schema && typeof t.args_schema === "object") {
    const schema = t.args_schema as Record<string, unknown>;
    if (typeof schema.model_json_schema === "function") {
      try {
        return (schema as any).model_json_schema();
      } catch {
        // fall through
      }
    }
  }

  if (typeof t.get_input_schema === "function") {
    try {
      const schema = (t as any).get_input_schema();
      if (typeof schema?.model_json_schema === "function") {
        return schema.model_json_schema();
      }
    } catch {
      // fall through
    }
  }

  for (const key of ["params_json_schema", "input_schema", "parameters", "schema"]) {
    const val = t[key];
    if (val && typeof val === "object" && !Array.isArray(val)) {
      return val as Record<string, unknown>;
    }
  }

  return { type: "object", properties: {} };
}

function _getToolCallable(toolObj: unknown): Function | null {
  if (typeof toolObj !== "object" || toolObj === null) return null;
  const t = toolObj as Record<string, unknown>;

  if (typeof t.func === "function") return t.func as Function;
  if (typeof t._run === "function") return t._run as Function;
  if (typeof toolObj === "function") return toolObj as Function;

  return null;
}
