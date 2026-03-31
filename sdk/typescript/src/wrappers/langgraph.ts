/**
 * Drop-in import wrapper for LangGraph.
 *
 * Re-exports everything from '@langchain/langgraph/prebuilt', but wraps
 * `createReactAgent` to capture llm/tools/prompt at creation time and
 * store them as extractable `_agentspan` metadata on the returned graph.
 *
 * Usage:
 *   // BEFORE: import { createReactAgent } from '@langchain/langgraph/prebuilt';
 *   // AFTER:
 *   import { createReactAgent } from '@agentspan-ai/sdk/langgraph';
 *
 * Everything else in user code stays UNCHANGED.
 */

// ── Lazy module loading ─────────────────────────────────

let _lgModule: Record<string, unknown> | null = null;

function _loadLangGraph(): Record<string, unknown> {
  if (_lgModule) return _lgModule;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _lgModule = require('@langchain/langgraph/prebuilt');
    return _lgModule!;
  } catch {
    throw new Error(
      `The '@langchain/langgraph' package is required by @agentspan-ai/sdk/langgraph but was not found. ` +
      `Install it with: npm install @langchain/langgraph`,
    );
  }
}

// ── Agentspan metadata interface ────────────────────────

/**
 * Metadata stored on the graph object by the wrapper.
 * Used by the LangGraph serializer for fast extraction.
 */
export interface AgentspanMetadata {
  model: string;
  tools: unknown[];
  instructions?: string;
  framework: 'langgraph';
}

// ── Model extraction from LLM ───────────────────────────

/**
 * Extract a provider/model string from a LangChain LLM instance.
 *
 * LangChain LLMs have various property names:
 * - ChatOpenAI: .model or .modelName
 * - ChatAnthropic: .model or .modelName
 * - ChatGoogleGenerativeAI: .model or .modelName
 */
export function extractModelFromLLM(llm: unknown): string {
  if (typeof llm === 'string') return llm;
  if (typeof llm !== 'object' || llm === null) return 'openai/gpt-4o-mini';

  const l = llm as Record<string, unknown>;

  const modelName =
    (typeof l.model === 'string' && l.model) ||
    (typeof l.modelName === 'string' && l.modelName) ||
    (typeof l.model_name === 'string' && l.model_name) ||
    'gpt-4o-mini';

  // Already has provider prefix
  if (modelName.includes('/')) return modelName;

  // Infer provider from class name
  const className = llm.constructor?.name ?? '';
  let provider = 'openai';

  if (className.includes('Anthropic') || className.includes('anthropic')) {
    provider = 'anthropic';
  } else if (className.includes('Google') || className.includes('Gemini') || className.includes('google')) {
    provider = 'google_gemini';
  } else if (className.includes('Bedrock') || className.includes('bedrock')) {
    provider = 'bedrock';
  } else if (className.includes('OpenAI') || className.includes('openai')) {
    provider = 'openai';
  } else {
    // Infer from model name
    provider = _inferProviderFromModel(modelName);
  }

  return `${provider}/${modelName}`;
}

function _inferProviderFromModel(modelName: string): string {
  if (modelName.startsWith('gpt-') || modelName.startsWith('o1') || modelName.startsWith('o3') || modelName.startsWith('o4')) return 'openai';
  if (modelName.includes('claude')) return 'anthropic';
  if (modelName.includes('gemini')) return 'google_gemini';
  return 'openai';
}

// ── createReactAgent wrapper ────────────────────────────

/**
 * Wrapped createReactAgent that captures llm/tools/prompt at creation
 * time and stores them as `_agentspan` metadata on the returned graph.
 *
 * The graph object is returned unchanged except for the added metadata.
 * When passed to `runtime.run()`, the LangGraph serializer will find
 * the `_agentspan` metadata and use it directly instead of introspection.
 */
export function createReactAgent(options: Record<string, unknown>): unknown {
  const original = _loadLangGraph().createReactAgent as Function;
  if (typeof original !== 'function') {
    throw new Error(
      `createReactAgent not found in '@langchain/langgraph/prebuilt'. ` +
      `Ensure you have a compatible version installed.`,
    );
  }

  // Call the original createReactAgent
  const graph = original(options);

  // Extract model/tools/prompt from options
  const llm = options.llm;
  const tools = (Array.isArray(options.tools) ? options.tools : []) as unknown[];
  const prompt = options.prompt;

  const modelStr = extractModelFromLLM(llm);

  // Store metadata on the graph for later extraction
  const metadata: AgentspanMetadata = {
    model: modelStr,
    tools,
    instructions: typeof prompt === 'string' ? prompt : undefined,
    framework: 'langgraph',
  };

  (graph as Record<string, unknown>)._agentspan = metadata;

  return graph;
}

// ── Re-export helper ────────────────────────────────────

/**
 * Get the underlying '@langchain/langgraph/prebuilt' module for pass-through
 * re-exports. Throws a helpful error if not installed.
 */
export function getLangGraphModule(): Record<string, unknown> {
  return _loadLangGraph();
}
