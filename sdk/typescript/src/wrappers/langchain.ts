/**
 * Drop-in import wrapper for LangChain.
 *
 * Wraps AgentExecutor (and RunnableSequence-based chains) to capture
 * the LLM and tools at construction time and store them as extractable
 * `_agentspan` metadata.
 *
 * Usage:
 *   // BEFORE: import { AgentExecutor } from 'langchain/agents';
 *   // AFTER:
 *   import { AgentExecutor } from '@agentspan-ai/sdk/langchain';
 *
 * Everything else in user code stays UNCHANGED.
 */

// ── Lazy module loading ─────────────────────────────────

let _lcCoreModule: Record<string, unknown> | null = null;

function _loadLangChainCore(): Record<string, unknown> {
  if (_lcCoreModule) return _lcCoreModule;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _lcCoreModule = require('@langchain/core/runnables');
    return _lcCoreModule!;
  } catch {
    throw new Error(
      `The '@langchain/core' package is required by @agentspan-ai/sdk/langchain but was not found. ` +
      `Install it with: npm install @langchain/core`,
    );
  }
}

// ── Agentspan metadata interface ────────────────────────

/**
 * Metadata stored on the executor/runnable by the wrapper.
 * Used by the LangChain serializer for fast extraction.
 */
export interface AgentspanMetadata {
  model: string;
  tools: unknown[];
  instructions?: string;
  framework: 'langchain';
}

// ── Model extraction from LLM ───────────────────────────

/**
 * Extract a provider/model string from a LangChain LLM instance.
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

// ── createAgentExecutor wrapper ─────────────────────────

/**
 * Create a LangChain AgentExecutor-like object that stores agentspan metadata.
 *
 * This wraps the common pattern of creating an agent with tools and an LLM.
 * It captures the LLM and tools at construction time.
 */
export function createAgentExecutor(options: {
  agent: unknown;
  tools: unknown[];
  llm?: unknown;
  verbose?: boolean;
  handleParsingErrors?: boolean;
  maxIterations?: number;
}): unknown {
  // Try to find the LLM from the agent if not provided directly
  let llm = options.llm;
  if (!llm && options.agent) {
    const a = options.agent as Record<string, unknown>;
    llm = a.llm
      ?? (a.llm_chain as Record<string, unknown> | undefined)?.llm
      ?? (a.runnable as Record<string, unknown> | undefined)?.first;
  }

  const modelStr = extractModelFromLLM(llm);

  // Build the executor (pass-through to real LangChain if available)
  let executor: Record<string, unknown>;
  try {
    const lcModule = _loadLangChainCore();
    const AgentExecutorClass = lcModule.AgentExecutor as new (opts: unknown) => Record<string, unknown>;
    if (typeof AgentExecutorClass === 'function') {
      executor = new AgentExecutorClass(options);
    } else {
      // Fallback: create a plain object that stores the configuration
      executor = {
        agent: options.agent,
        tools: options.tools,
        verbose: options.verbose ?? false,
        handleParsingErrors: options.handleParsingErrors ?? false,
        maxIterations: options.maxIterations,
      };
    }
  } catch {
    // Fallback: create a plain object
    executor = {
      agent: options.agent,
      tools: options.tools,
      verbose: options.verbose ?? false,
      handleParsingErrors: options.handleParsingErrors ?? false,
      maxIterations: options.maxIterations,
    };
  }

  // Store metadata for agentspan extraction
  const metadata: AgentspanMetadata = {
    model: modelStr,
    tools: options.tools,
    instructions: undefined,
    framework: 'langchain',
  };

  executor._agentspan = metadata;

  return executor;
}

// ── RunnableLambda wrapper ──────────────────────────────

/**
 * Create a LangChain RunnableLambda that stores agentspan metadata.
 *
 * This wraps the common pattern of creating a custom runnable with
 * an LLM and tools in the closure.
 */
export function createRunnableWithMetadata(options: {
  func: Function;
  llm?: unknown;
  tools?: unknown[];
  instructions?: string;
}): unknown {
  const modelStr = extractModelFromLLM(options.llm);

  // Create a plain object that mimics a runnable with metadata
  const runnable: Record<string, unknown> = {
    invoke: options.func,
    lc_namespace: ['langchain', 'schema', 'runnable'],
    tools: options.tools ?? [],
    _agentspan: {
      model: modelStr,
      tools: options.tools ?? [],
      instructions: options.instructions,
      framework: 'langchain',
    } as AgentspanMetadata,
  };

  return runnable;
}

// ── Re-export helper ────────────────────────────────────

/**
 * Get the underlying '@langchain/core' module for pass-through re-exports.
 * Throws a helpful error if not installed.
 */
export function getLangChainModule(): Record<string, unknown> {
  return _loadLangChainCore();
}
