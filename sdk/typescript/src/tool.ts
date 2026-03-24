import { createRequire } from 'node:module';
import type { ToolDef, ToolType, ToolContext, CredentialFile } from './types.js';
import { ConfigurationError } from './errors.js';

const require = createRequire(import.meta.url);

// ── Symbol for attaching ToolDef metadata ─────────────────

const TOOL_DEF: unique symbol = Symbol('TOOL_DEF');

// ── Type for the callable returned by tool() ──────────────

/**
 * A callable async function with attached ToolDef metadata.
 */
export type ToolFunction<TInput = unknown, TOutput = unknown> = ((
  args: TInput,
  ctx?: ToolContext,
) => Promise<TOutput>) & {
  readonly [TOOL_DEF]: ToolDef;
};

// ── Schema detection helpers ──────────────────────────────

/**
 * Returns true if `obj` looks like a Zod schema (has `._def` property).
 */
export function isZodSchema(obj: unknown): boolean {
  return obj != null && typeof obj === 'object' && '_def' in obj;
}

/**
 * Convert a Zod schema or JSON Schema object to JSON Schema.
 * If it's already JSON Schema, returns as-is.
 * Uses Zod v4's built-in z.toJSONSchema() — no external dependency needed.
 */
/**
 * Convert a Zod schema to JSON Schema.
 * Supports both Zod v3 (via zod-to-json-schema) and Zod v4 (built-in z.toJSONSchema).
 */
async function zodSchemaToJson(schema: unknown): Promise<object> {
  // Try Zod v4 built-in first (z.toJSONSchema exists on the module)
  try {
    const zod = await import('zod');
    if (typeof (zod as any).toJSONSchema === 'function') {
      return (zod as any).toJSONSchema(schema) as object;
    }
  } catch { /* fall through */ }

  // Fall back to zod-to-json-schema (works with Zod v3)
  try {
    const { zodToJsonSchema } = await import('zod-to-json-schema');
    return zodToJsonSchema(schema as any, { target: 'jsonSchema7' });
  } catch { /* fall through */ }

  throw new ConfigurationError('Cannot convert Zod schema to JSON Schema. Install zod-to-json-schema or use Zod v4+.');
}

// Synchronous version using cached converter
let _zodConverter: ((schema: unknown) => object) | null = null;

function initZodConverter(): void {
  if (_zodConverter) return;
  try {
    // Try Zod v4 built-in
    const zod = require('zod');
    if (typeof zod.toJSONSchema === 'function') {
      _zodConverter = (s: unknown) => zod.toJSONSchema(s) as object;
      return;
    }
  } catch { /* fall through */ }

  try {
    // Fall back to zod-to-json-schema
    const { zodToJsonSchema } = require('zod-to-json-schema');
    _zodConverter = (s: unknown) => zodToJsonSchema(s as any, { target: 'jsonSchema7' });
    return;
  } catch { /* fall through */ }

  _zodConverter = () => { throw new ConfigurationError('No Zod-to-JSON-Schema converter available'); };
}

export function toJsonSchema(schema: unknown): object {
  if (isZodSchema(schema)) {
    initZodConverter();
    return _zodConverter!(schema);
  }
  return schema as object;
}

// ── tool() ────────────────────────────────────────────────

export interface ToolOptions<TInput = unknown, TOutput = unknown> {
  name?: string;
  description: string;
  inputSchema: unknown; // Zod schema or JSON Schema object
  outputSchema?: unknown;
  approvalRequired?: boolean;
  timeoutSeconds?: number;
  external?: boolean;
  isolated?: boolean;
  credentials?: (string | CredentialFile)[];
  guardrails?: unknown[];
}

/**
 * Wraps an async function as an agent tool with metadata.
 *
 * Accepts Zod schemas or JSON Schema objects for `inputSchema` and `outputSchema`.
 * Zod schemas are converted to JSON Schema at definition time.
 */
export function tool<TInput = unknown, TOutput = unknown>(
  fn: (args: TInput, ctx?: ToolContext) => Promise<TOutput>,
  options: ToolOptions<TInput, TOutput>,
): ToolFunction<TInput, TOutput> {
  const name = options.name || fn.name || 'unnamed_tool';
  const inputSchema = toJsonSchema(options.inputSchema);
  const outputSchema = options.outputSchema
    ? toJsonSchema(options.outputSchema)
    : undefined;

  const def: ToolDef = {
    name,
    description: options.description,
    inputSchema,
    toolType: 'worker',
    func: options.external ? null : fn,
    ...(outputSchema !== undefined && { outputSchema }),
    ...(options.approvalRequired !== undefined && {
      approvalRequired: options.approvalRequired,
    }),
    ...(options.timeoutSeconds !== undefined && {
      timeoutSeconds: options.timeoutSeconds,
    }),
    ...(options.external !== undefined && { external: options.external }),
    ...(options.isolated !== undefined && { isolated: options.isolated }),
    ...(options.credentials !== undefined && {
      credentials: options.credentials,
    }),
    ...(options.guardrails !== undefined && { guardrails: options.guardrails }),
  };

  // Create the wrapper function
  const wrapper = async (args: TInput, ctx?: ToolContext): Promise<TOutput> => {
    return fn(args, ctx);
  };

  // Attach metadata via symbol
  Object.defineProperty(wrapper, TOOL_DEF, {
    value: def,
    writable: false,
    enumerable: false,
    configurable: false,
  });

  // Preserve function name
  Object.defineProperty(wrapper, 'name', { value: name });

  return wrapper as ToolFunction<TInput, TOutput>;
}

// ── getToolDef() ──────────────────────────────────────────

/**
 * Check if an object is a Vercel AI SDK tool shape
 * (has inputSchema as Zod + execute function).
 */
function isVercelAITool(obj: unknown): boolean {
  return (
    obj != null &&
    typeof obj === 'object' &&
    'execute' in obj &&
    typeof (obj as Record<string, unknown>).execute === 'function' &&
    'parameters' in obj &&
    isZodSchema((obj as Record<string, unknown>).parameters)
  );
}

/**
 * Check if an object has the TOOL_DEF symbol (agentspan tool wrapper).
 * Tool wrappers are functions, so we check both object and function types.
 */
function hasToolDef(obj: unknown): boolean {
  return (
    obj != null &&
    (typeof obj === 'object' || typeof obj === 'function') &&
    TOOL_DEF in (obj as object)
  );
}

/**
 * Check if an object is a raw ToolDef (has name + description + inputSchema).
 */
function isRawToolDef(obj: unknown): boolean {
  if (obj == null || typeof obj !== 'object') return false;
  const o = obj as Record<string, unknown>;
  return (
    typeof o.name === 'string' &&
    typeof o.description === 'string' &&
    o.inputSchema != null &&
    typeof o.inputSchema === 'object'
  );
}

/**
 * Wrap a Vercel AI SDK tool object into a ToolDef.
 */
function wrapVercelAITool(aiTool: Record<string, unknown>): ToolDef {
  const params = aiTool.parameters;
  const jsonSchema = toJsonSchema(params);
  const executeFn = aiTool.execute as Function;
  const description =
    typeof aiTool.description === 'string' ? aiTool.description : '';
  const name =
    typeof aiTool.description === 'string'
      ? aiTool.description.slice(0, 30).replace(/\s+/g, '_')
      : 'ai_tool';

  const wrapped = tool(
    async (args: unknown) => executeFn(args, {}),
    {
      name,
      description,
      inputSchema: jsonSchema,
    },
  );
  return getToolDef(wrapped);
}

/**
 * Extract ToolDef from any supported tool format:
 * 1. agentspan tool() wrapper (via Symbol)
 * 2. Vercel AI SDK tool (has parameters as Zod + execute)
 * 3. Raw ToolDef object
 *
 * Throws ConfigurationError if format is unrecognized.
 */
export function getToolDef(obj: unknown): ToolDef {
  // 1. agentspan tool() wrapper
  if (hasToolDef(obj)) {
    return (obj as Record<symbol, ToolDef>)[TOOL_DEF];
  }

  // 2. Vercel AI SDK tool
  if (isVercelAITool(obj)) {
    return wrapVercelAITool(obj as Record<string, unknown>);
  }

  // 3. Raw ToolDef object
  if (isRawToolDef(obj)) {
    const raw = obj as Record<string, unknown>;
    return {
      name: raw.name as string,
      description: raw.description as string,
      inputSchema: raw.inputSchema as object,
      toolType: (raw.toolType as ToolType) ?? 'worker',
      ...(raw.func !== undefined && { func: raw.func as Function | null }),
      ...(raw.outputSchema !== undefined && {
        outputSchema: raw.outputSchema as object,
      }),
      ...(raw.approvalRequired !== undefined && {
        approvalRequired: raw.approvalRequired as boolean,
      }),
      ...(raw.timeoutSeconds !== undefined && {
        timeoutSeconds: raw.timeoutSeconds as number,
      }),
      ...(raw.external !== undefined && { external: raw.external as boolean }),
      ...(raw.isolated !== undefined && { isolated: raw.isolated as boolean }),
      ...(raw.credentials !== undefined && {
        credentials: raw.credentials as (string | CredentialFile)[],
      }),
      ...(raw.guardrails !== undefined && {
        guardrails: raw.guardrails as unknown[],
      }),
      ...(raw.config !== undefined && {
        config: raw.config as Record<string, unknown>,
      }),
    };
  }

  throw new ConfigurationError(
    `Unrecognized tool format: ${typeof obj}`,
  );
}

/**
 * Auto-detect format and return ToolDef.
 * Handles agentspan tool(), Vercel AI SDK tool, and raw ToolDef objects.
 */
export function normalizeToolInput(input: unknown): ToolDef {
  return getToolDef(input);
}

// ── Server-side tool constructors ─────────────────────────

// Helper to build a ToolDef with func=null
function serverTool(
  toolType: ToolType,
  name: string,
  description: string,
  inputSchema: object | undefined,
  config: Record<string, unknown>,
  extras?: Partial<ToolDef>,
): ToolDef {
  return {
    name,
    description,
    inputSchema: inputSchema
      ? toJsonSchema(inputSchema)
      : { type: 'object', properties: {} },
    toolType,
    func: null,
    config,
    ...extras,
  };
}

// ── httpTool ──────────────────────────────────────────────

export interface HttpToolOptions {
  name: string;
  description: string;
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  headers?: Record<string, string>;
  inputSchema?: unknown;
  accept?: string[];
  contentType?: string;
  credentials?: (string | CredentialFile)[];
}

export function httpTool(opts: HttpToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    url: opts.url,
    method: opts.method ?? 'GET',
  };
  if (opts.headers) config.headers = opts.headers;
  if (opts.accept) config.accept = opts.accept;
  if (opts.contentType) config.contentType = opts.contentType;
  if (opts.credentials) config.credentials = opts.credentials;

  return serverTool(
    'http',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── mcpTool ───────────────────────────────────────────────

export interface McpToolOptions {
  serverUrl: string;
  name?: string;
  description?: string;
  headers?: Record<string, string>;
  toolNames?: string[];
  maxTools?: number;
  credentials?: (string | CredentialFile)[];
}

export function mcpTool(opts: McpToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    serverUrl: opts.serverUrl,
  };
  if (opts.headers) config.headers = opts.headers;
  if (opts.toolNames) config.toolNames = opts.toolNames;
  if (opts.maxTools !== undefined) config.maxTools = opts.maxTools;
  if (opts.credentials) config.credentials = opts.credentials;

  return serverTool(
    'mcp',
    opts.name ?? 'mcp_tool',
    opts.description ?? 'MCP tool',
    undefined,
    config,
  );
}

// ── apiTool ───────────────────────────────────────────────

export interface ApiToolOptions {
  url: string;
  name?: string;
  description?: string;
  headers?: Record<string, string>;
  toolNames?: string[];
  maxTools?: number;
  credentials?: (string | CredentialFile)[];
}

export function apiTool(opts: ApiToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    url: opts.url,
  };
  if (opts.headers) config.headers = opts.headers;
  if (opts.toolNames) config.toolNames = opts.toolNames;
  if (opts.maxTools !== undefined) config.maxTools = opts.maxTools;
  if (opts.credentials) config.credentials = opts.credentials;

  return serverTool(
    'api',
    opts.name ?? 'api_tool',
    opts.description ?? 'API tool',
    undefined,
    config,
  );
}

// ── agentTool ─────────────────────────────────────────────

export interface AgentToolOptions {
  name?: string;
  description?: string;
  retryCount?: number;
  retryDelaySeconds?: number;
  optional?: boolean;
}

/**
 * Wraps an Agent as a callable tool (sub-agent execution).
 * The `agent` parameter is typed as `unknown` to avoid circular dependency;
 * it must be an Agent instance at runtime.
 */
export function agentTool(
  agent: unknown,
  opts?: AgentToolOptions,
): ToolDef {
  // Extract name from agent for defaults
  const agentObj = agent as { name?: string };
  const agentName = agentObj.name ?? 'agent';
  const name = opts?.name ?? `${agentName}_tool`;
  const description = opts?.description ?? `Run ${agentName} as a tool`;

  const config: Record<string, unknown> = {
    agent,
  };
  if (opts?.retryCount !== undefined) config.retryCount = opts.retryCount;
  if (opts?.retryDelaySeconds !== undefined)
    config.retryDelaySeconds = opts.retryDelaySeconds;
  if (opts?.optional !== undefined) config.optional = opts.optional;

  return serverTool('agent_tool', name, description, undefined, config);
}

// ── humanTool ─────────────────────────────────────────────

export interface HumanToolOptions {
  name: string;
  description: string;
  inputSchema?: unknown;
}

export function humanTool(opts: HumanToolOptions): ToolDef {
  return serverTool(
    'human',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    {},
  );
}

// ── imageTool ─────────────────────────────────────────────

export interface ImageToolOptions {
  name: string;
  description: string;
  llmProvider: string;
  model: string;
  inputSchema?: unknown;
  style?: string;
  size?: string;
}

export function imageTool(opts: ImageToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    llmProvider: opts.llmProvider,
    model: opts.model,
  };
  if (opts.style) config.style = opts.style;
  if (opts.size) config.size = opts.size;

  return serverTool(
    'generate_image',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── audioTool ─────────────────────────────────────────────

export interface AudioToolOptions {
  name: string;
  description: string;
  llmProvider: string;
  model: string;
  inputSchema?: unknown;
  voice?: string;
  speed?: number;
  format?: string;
}

export function audioTool(opts: AudioToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    llmProvider: opts.llmProvider,
    model: opts.model,
  };
  if (opts.voice) config.voice = opts.voice;
  if (opts.speed !== undefined) config.speed = opts.speed;
  if (opts.format) config.format = opts.format;

  return serverTool(
    'generate_audio',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── videoTool ─────────────────────────────────────────────

export interface VideoToolOptions {
  name: string;
  description: string;
  llmProvider: string;
  model: string;
  inputSchema?: unknown;
  duration?: number;
  resolution?: string;
  fps?: number;
  style?: string;
  aspectRatio?: string;
}

export function videoTool(opts: VideoToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    llmProvider: opts.llmProvider,
    model: opts.model,
  };
  if (opts.duration !== undefined) config.duration = opts.duration;
  if (opts.resolution) config.resolution = opts.resolution;
  if (opts.fps !== undefined) config.fps = opts.fps;
  if (opts.style) config.style = opts.style;
  if (opts.aspectRatio) config.aspectRatio = opts.aspectRatio;

  return serverTool(
    'generate_video',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── pdfTool ───────────────────────────────────────────────

export interface PdfToolOptions {
  name?: string;
  description?: string;
  inputSchema?: unknown;
  pageSize?: string;
  theme?: string;
  fontSize?: number;
}

export function pdfTool(opts?: PdfToolOptions): ToolDef {
  const config: Record<string, unknown> = {};
  if (opts?.pageSize) config.pageSize = opts.pageSize;
  if (opts?.theme) config.theme = opts.theme;
  if (opts?.fontSize !== undefined) config.fontSize = opts.fontSize;

  return serverTool(
    'generate_pdf',
    opts?.name ?? 'generate_pdf',
    opts?.description ?? 'Generate a PDF document',
    opts?.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── searchTool (RAG) ──────────────────────────────────────

export interface SearchToolOptions {
  name: string;
  description: string;
  vectorDb: string;
  index: string;
  embeddingModelProvider: string;
  embeddingModel: string;
  namespace?: string;
  maxResults?: number;
  dimensions?: number;
  inputSchema?: unknown;
}

export function searchTool(opts: SearchToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    vectorDb: opts.vectorDb,
    index: opts.index,
    embeddingModelProvider: opts.embeddingModelProvider,
    embeddingModel: opts.embeddingModel,
    namespace: opts.namespace ?? 'default_ns',
    maxResults: opts.maxResults ?? 5,
  };
  if (opts.dimensions !== undefined) config.dimensions = opts.dimensions;

  return serverTool(
    'rag_search',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── indexTool (RAG) ───────────────────────────────────────

export interface IndexToolOptions {
  name: string;
  description: string;
  vectorDb: string;
  index: string;
  embeddingModelProvider: string;
  embeddingModel: string;
  namespace?: string;
  chunkSize?: number;
  chunkOverlap?: number;
  dimensions?: number;
  inputSchema?: unknown;
}

export function indexTool(opts: IndexToolOptions): ToolDef {
  const config: Record<string, unknown> = {
    vectorDb: opts.vectorDb,
    index: opts.index,
    embeddingModelProvider: opts.embeddingModelProvider,
    embeddingModel: opts.embeddingModel,
    namespace: opts.namespace ?? 'default_ns',
  };
  if (opts.chunkSize !== undefined) config.chunkSize = opts.chunkSize;
  if (opts.chunkOverlap !== undefined) config.chunkOverlap = opts.chunkOverlap;
  if (opts.dimensions !== undefined) config.dimensions = opts.dimensions;

  return serverTool(
    'rag_index',
    opts.name,
    opts.description,
    opts.inputSchema ? toJsonSchema(opts.inputSchema) : undefined,
    config,
  );
}

// ── @Tool decorator ───────────────────────────────────────

const TOOL_DECORATOR_KEY = Symbol('TOOL_DECORATOR');

interface ToolDecoratorOptions {
  name?: string;
  description?: string;
  inputSchema?: unknown;
  outputSchema?: unknown;
  approvalRequired?: boolean;
  timeoutSeconds?: number;
  external?: boolean;
  isolated?: boolean;
  credentials?: (string | CredentialFile)[];
  guardrails?: unknown[];
}

/**
 * Class method decorator that marks a method as an agent tool.
 * Use `toolsFrom(instance)` to extract decorated methods as tool() wrappers.
 */
export function Tool(options?: ToolDecoratorOptions) {
  return function (
    target: object,
    propertyKey: string,
    descriptor: PropertyDescriptor,
  ): void {
    // Store decorator options on the descriptor's value
    const metadata: ToolDecoratorOptions & { _methodName: string } = {
      ...options,
      _methodName: propertyKey,
    };

    if (!descriptor.value) return;

    // Store metadata on the function
    Object.defineProperty(descriptor.value, TOOL_DECORATOR_KEY, {
      value: metadata,
      writable: false,
      enumerable: false,
      configurable: false,
    });
  };
}

/**
 * Extract all @Tool-decorated methods from a class instance as tool() wrappers,
 * bound to the instance.
 */
export function toolsFrom(
  instance: object,
): ToolFunction<unknown, unknown>[] {
  const tools: ToolFunction<unknown, unknown>[] = [];
  const proto = Object.getPrototypeOf(instance);
  const propertyNames = Object.getOwnPropertyNames(proto);

  for (const key of propertyNames) {
    if (key === 'constructor') continue;
    const descriptor = Object.getOwnPropertyDescriptor(proto, key);
    if (!descriptor?.value || typeof descriptor.value !== 'function') continue;

    const metadata = (descriptor.value as Record<symbol, unknown>)[
      TOOL_DECORATOR_KEY
    ] as (ToolDecoratorOptions & { _methodName: string }) | undefined;

    if (!metadata) continue;

    const methodName = metadata._methodName;
    const boundFn = descriptor.value.bind(instance);

    const toolName = metadata.name ?? methodName;
    const description =
      metadata.description ?? `Tool: ${toolName}`;
    const inputSchema = metadata.inputSchema ?? {
      type: 'object',
      properties: {},
    };

    const wrapped = tool(boundFn, {
      name: toolName,
      description,
      inputSchema,
      outputSchema: metadata.outputSchema,
      approvalRequired: metadata.approvalRequired,
      timeoutSeconds: metadata.timeoutSeconds,
      external: metadata.external,
      isolated: metadata.isolated,
      credentials: metadata.credentials,
      guardrails: metadata.guardrails,
    });

    tools.push(wrapped);
  }

  return tools;
}
