/**
 * Drop-in import wrapper for Vercel AI SDK.
 *
 * Re-exports everything from 'ai', but wraps `generateText` and `streamText`
 * to intercept the options object, extract model/tools/system, compile to
 * AgentConfig, and run on agentspan.
 *
 * Usage:
 *   // BEFORE: import { generateText } from 'ai';
 *   // AFTER:
 *   import { generateText } from '@agentspan-ai/sdk/vercel-ai';
 *
 * Everything else in user code stays UNCHANGED.
 */

// Re-export everything from 'ai' unchanged
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _ai: any = null;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function _loadAI(): Promise<any> {
  if (_ai) return _ai;
  try {
    // @ts-expect-error 'ai' is an optional peer dependency
    _ai = await import('ai');
    return _ai;
  } catch {
    throw new Error(
      `The 'ai' package is required by @agentspan-ai/sdk/vercel-ai but was not found. ` +
      `Install it with: npm install ai`,
    );
  }
}

// Eagerly attempt to load 'ai' for re-exports
// This will be available synchronously after the first access
let _aiModule: Record<string, unknown> | null = null;
try {
  // Use dynamic import to load the module
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  _aiModule = require('ai');
} catch {
  // Will be loaded lazily on first use
}

// ── Re-exports ──────────────────────────────────────────

// We can't use `export * from 'ai'` because 'ai' is an optional peer dep.
// Instead, we provide a proxy-based re-export and explicit wrapped functions.

// ── Model string extraction ─────────────────────────────

/**
 * Extract a provider/model string from an AI SDK model object.
 *
 * AI SDK model objects typically have:
 * - .modelId: the model identifier (e.g., 'gpt-4o-mini')
 * - .provider: the provider string (e.g., 'openai.chat')
 *
 * Some models use .modelName or .model instead.
 */
export function extractModelString(model: unknown): string {
  if (typeof model === 'string') return model;
  if (typeof model !== 'object' || model === null) return 'openai/gpt-4o-mini';

  const m = model as Record<string, unknown>;

  // AI SDK v4 model objects: .modelId and .provider
  const modelId =
    (typeof m.modelId === 'string' && m.modelId) ||
    (typeof m.modelName === 'string' && m.modelName) ||
    (typeof m.model === 'string' && m.model) ||
    'gpt-4o-mini';

  // Already has provider prefix
  if (modelId.includes('/')) return modelId;

  // Extract provider from .provider string (e.g., 'openai.chat' -> 'openai')
  let provider = 'openai';
  if (typeof m.provider === 'string' && m.provider) {
    provider = m.provider.split('.')[0];
  } else if (typeof m.providerId === 'string' && m.providerId) {
    provider = m.providerId;
  } else {
    // Infer from model name
    provider = _inferProviderFromModelName(modelId);
  }

  return `${provider}/${modelId}`;
}

function _inferProviderFromModelName(modelName: string): string {
  if (modelName.startsWith('gpt-') || modelName.startsWith('o1') || modelName.startsWith('o3') || modelName.startsWith('o4')) return 'openai';
  if (modelName.includes('claude')) return 'anthropic';
  if (modelName.includes('gemini')) return 'google';
  if (modelName.includes('llama') || modelName.includes('mixtral')) return 'groq';
  return 'openai';
}

// ── Tool extraction ─────────────────────────────────────

/**
 * Extract agentspan-compatible tools from AI SDK tools Record.
 *
 * AI SDK tools are Record<string, CoreTool> where each CoreTool has:
 * - .parameters: Zod schema
 * - .execute: async function
 * - .description?: string
 */
function _extractTools(tools: Record<string, unknown> | undefined): unknown[] {
  if (!tools || typeof tools !== 'object') return [];
  return Object.values(tools);
}

// ── Finish reason mapping ───────────────────────────────

export function mapFinishReason(reason: string | undefined): string {
  switch (reason) {
    case 'stop': return 'stop';
    case 'length': return 'length';
    case 'tool_calls':
    case 'tool-calls': return 'tool-calls';
    case 'content-filter': return 'content-filter';
    default: return reason ?? 'stop';
  }
}

// ── generateText wrapper ────────────────────────────────

import { Agent, AgentRuntime } from '../index.js';

/**
 * Wrapped generateText that runs on agentspan.
 *
 * Intercepts the options object, extracts model/tools/system/prompt,
 * compiles to an Agent, runs on agentspan, returns the same result type.
 */
export async function generateText(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  const model = options.model;
  const tools = options.tools as Record<string, unknown> | undefined;
  const system = options.system as string | undefined;
  const prompt = options.prompt as string | undefined;
  const maxSteps = options.maxSteps as number | undefined;
  const messages = options.messages as unknown[] | undefined;

  // Build model string from AI SDK model object
  const modelStr = extractModelString(model);

  // Extract tool objects for the agent
  const toolObjects = _extractTools(tools);

  // Build native Agent
  const agent = new Agent({
    name: 'vercel_ai_agent',
    model: modelStr,
    instructions: system,
    tools: toolObjects,
    maxTurns: maxSteps ?? 25,
  });

  // Run on agentspan
  const runtime = new AgentRuntime();
  try {
    const promptStr = prompt ?? (messages ? JSON.stringify(messages) : '');
    const result = await runtime.run(agent, promptStr);

    // Map agentspan result back to Vercel AI SDK result format
    return {
      text: typeof result.output?.result === 'string'
        ? result.output.result
        : JSON.stringify(result.output),
      toolCalls: result.toolCalls ?? [],
      toolResults: [],
      finishReason: mapFinishReason(result.finishReason),
      usage: result.tokenUsage ? {
        promptTokens: result.tokenUsage.promptTokens,
        completionTokens: result.tokenUsage.completionTokens,
        totalTokens: result.tokenUsage.totalTokens,
      } : undefined,
      steps: [],
      response: {},
      warnings: [],
      roundtrips: [],
      experimental_providerMetadata: {},
    };
  } finally {
    await runtime.shutdown();
  }
}

// ── streamText wrapper ──────────────────────────────────

/**
 * Wrapped streamText that runs on agentspan.
 *
 * For now, this delegates to generateText and wraps the result
 * in a stream-compatible interface. Full streaming will be added later.
 */
export async function streamText(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  // For now, run as generateText and return a stream-like wrapper
  const result = await generateText(options);

  return {
    ...result,
    textStream: (async function* () {
      yield result.text as string;
    })(),
    fullStream: (async function* () {
      yield { type: 'text-delta', textDelta: result.text as string };
    })(),
    toAIStream: () => {
      throw new Error('toAIStream() is not supported in the agentspan wrapper. Use textStream instead.');
    },
    toTextStreamResponse: () => {
      throw new Error('toTextStreamResponse() is not supported in the agentspan wrapper. Use textStream instead.');
    },
  };
}

// ── Proxy-based re-exports ──────────────────────────────

/**
 * Get the underlying 'ai' module for pass-through re-exports.
 * Throws a helpful error if the 'ai' package is not installed.
 */
export function getAIModule(): Record<string, unknown> {
  if (_aiModule) return _aiModule;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _aiModule = require('ai');
    return _aiModule!;
  } catch {
    throw new Error(
      `The 'ai' package is required by @agentspan-ai/sdk/vercel-ai but was not found. ` +
      `Install it with: npm install ai`,
    );
  }
}
