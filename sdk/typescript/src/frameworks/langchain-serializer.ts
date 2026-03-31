/**
 * LangChain AgentExecutor serializer — full extraction.
 *
 * Extracts model and tools from a LangChain AgentExecutor or Runnable,
 * producing (rawConfig, WorkerInfo[]) for server-side workflow compilation.
 *
 * No passthrough fallback — throws ConfigurationError if extraction fails.
 */

import { ConfigurationError } from '../errors.js';
import type { WorkerInfo } from './serializer.js';

const _DEFAULT_NAME = 'langchain_agent';

// ── Public API ──────────────────────────────────────────

/**
 * Serialize a LangChain AgentExecutor into (rawConfig, WorkerInfo[]).
 *
 * @throws ConfigurationError if model and tools cannot be extracted.
 */
export function serializeLangChain(
  executor: unknown,
): [Record<string, unknown>, WorkerInfo[]] {
  const e = executor as Record<string, unknown>;
  const name = (typeof e.name === 'string' && e.name) || _DEFAULT_NAME;

  // Check for wrapper metadata first (set by @agentspan-ai/sdk/langchain wrapper)
  const metadata = e._agentspan as Record<string, unknown> | undefined;
  if (metadata?.model && metadata?.tools) {
    return _serializeFromMetadata(name, metadata);
  }

  const modelStr = _extractModelFromExecutor(executor);
  const tools = (Array.isArray(e.tools) && e.tools) || [];

  if (modelStr && tools.length > 0) {
    return _serializeFullExtraction(name, modelStr, tools);
  }

  // No extraction possible — throw error
  throw new ConfigurationError(
    `Cannot extract from LangChain executor. ` +
    `Model: ${modelStr ?? 'not found'}, Tools: ${tools.length}. ` +
    `Use AgentExecutor with an LLM and tools, or create a native agentspan Agent.`,
  );
}

// ── Wrapper metadata extraction ─────────────────────────

/**
 * Serialize from wrapper-captured metadata (set by @agentspan-ai/sdk/langchain).
 * Uses the model/tools/instructions stored on the executor by the wrapper.
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
): [Record<string, unknown>, WorkerInfo[]] {
  const rawConfig: Record<string, unknown> = { name, model: modelStr };
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

// ── Model extraction ────────────────────────────────────

function _extractModelFromExecutor(executor: unknown): string | null {
  if (typeof executor !== 'object' || executor === null) return null;

  // Try common paths to the LLM
  const paths: string[][] = [
    ['agent', 'llm'],
    ['agent', 'llm_chain', 'llm'],
    ['agent', 'runnable', 'first'],
    ['llm'],
  ];

  for (const path of paths) {
    let obj: unknown = executor;
    for (const attr of path) {
      if (typeof obj !== 'object' || obj === null) {
        obj = null;
        break;
      }
      obj = (obj as Record<string, unknown>)[attr];
    }
    if (obj != null) {
      const result = _tryGetModelString(obj);
      if (result) return result;
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

  if (typeof t.func === 'function') return t.func as Function;
  if (typeof t._run === 'function') return t._run as Function;
  if (typeof toolObj === 'function') return toolObj as Function;

  return null;
}
