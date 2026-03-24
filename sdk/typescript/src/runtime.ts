import type {
  AgentResult,
  AgentEvent,
  AgentStatus,
  DeploymentInfo,
  RunOptions,
  ToolDef,
} from './types.js';
import { AgentAPIError, AgentspanError } from './errors.js';
import { AgentConfig } from './config.js';
import type { AgentConfigOptions } from './config.js';
import { Agent } from './agent.js';
import { AgentConfigSerializer } from './serializer.js';
import { getToolDef } from './tool.js';
import { WorkerManager } from './worker.js';
import { AgentStream } from './stream.js';
import { makeAgentResult } from './result.js';
import { TERMINAL_STATUSES } from './result.js';

// ── Framework detection stub ────────────────────────────

/**
 * Stub for framework detection. Returns null (no framework detected).
 * Will be replaced by actual detection in a future chunk.
 */
function detectFramework(_agent: unknown): null {
  return null;
}

// ── AgentHandle ─────────────────────────────────────────

/**
 * Handle to a running agent workflow.
 * Returned by `start()` for async interaction.
 */
export interface AgentHandle {
  readonly workflowId: string;
  readonly correlationId: string;
  getStatus(): Promise<AgentStatus>;
  wait(pollIntervalMs?: number): Promise<AgentResult>;
  respond(output: unknown): Promise<void>;
  approve(output?: Record<string, unknown>): Promise<void>;
  reject(reason?: string): Promise<void>;
  send(message: string): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  cancel(): Promise<void>;
  stream(): AgentStream;
}

// ── AgentRuntime ────────────────────────────────────────

/**
 * Core execution runtime for the Agentspan SDK.
 * Manages agent lifecycle: run, start, stream, deploy, plan, serve.
 */
export class AgentRuntime {
  readonly config: AgentConfig;
  private readonly authHeaders: Record<string, string>;
  private readonly serializer: AgentConfigSerializer;
  private readonly workerManager: WorkerManager;

  constructor(options?: AgentConfigOptions) {
    this.config = new AgentConfig(options);
    this.authHeaders = this._buildAuthHeaders();
    this.serializer = new AgentConfigSerializer();
    this.workerManager = new WorkerManager(
      this.config.serverUrl,
      this.authHeaders,
      this.config.workerPollIntervalMs,
    );
  }

  // ── run() ─────────────────────────────────────────────

  /**
   * Run an agent synchronously: start, register workers, stream events, return result.
   */
  async run(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentResult> {
    const framework = detectFramework(agent);
    if (framework !== null) {
      return this._runFramework(agent, prompt, framework, options);
    }

    const correlationId = generateCorrelationId();

    // Serialize agent config
    const payload = this.serializer.serialize(agent, prompt, {
      sessionId: options?.sessionId,
      media: options?.media,
      idempotencyKey: options?.idempotencyKey,
    });

    if (options?.timeoutSeconds !== undefined) {
      payload.timeoutSeconds = options.timeoutSeconds;
    }

    // Register workers for all tools
    await this._registerAllWorkers(agent);
    this.workerManager.startPolling();

    try {
      // Start agent
      const startResponse = await this._httpRequest(
        'POST',
        '/agent/start',
        payload,
        options?.signal,
      );

      const workflowId = startResponse.workflowId as string;

      // Create SSE stream
      const sseUrl = `${this.config.serverUrl}/agent/${workflowId}/sse`;
      const agentStream = new AgentStream(
        sseUrl,
        this.authHeaders,
        workflowId,
        async (body) => this._respond(workflowId, body, options?.signal),
        this.config.serverUrl,
      );

      // Drain all events
      const events: AgentEvent[] = [];
      for await (const event of agentStream) {
        events.push(event);
      }

      // Get final status for token usage
      let tokenUsage;
      try {
        const status = await this._getStatus(workflowId, options?.signal);
        tokenUsage = (status as unknown as Record<string, unknown>).tokenUsage as
          | AgentResult['tokenUsage']
          | undefined;
      } catch {
        // Non-critical
      }

      // Build result from stream
      const result = await agentStream.getResult();
      if (tokenUsage) {
        (result as unknown as Record<string, unknown>).tokenUsage = tokenUsage;
      }
      (result as unknown as Record<string, unknown>).correlationId = correlationId;

      return result;
    } finally {
      this.workerManager.stopPolling();
    }
  }

  // ── start() ───────────────────────────────────────────

  /**
   * Start an agent asynchronously. Returns a handle for interaction.
   */
  async start(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentHandle> {
    const framework = detectFramework(agent);
    if (framework !== null) {
      throw new AgentspanError('Framework not yet implemented');
    }

    const correlationId = generateCorrelationId();

    const payload = this.serializer.serialize(agent, prompt, {
      sessionId: options?.sessionId,
      media: options?.media,
      idempotencyKey: options?.idempotencyKey,
    });

    if (options?.timeoutSeconds !== undefined) {
      payload.timeoutSeconds = options.timeoutSeconds;
    }

    // Register workers
    await this._registerAllWorkers(agent);
    this.workerManager.startPolling();

    // Start agent
    const startResponse = await this._httpRequest(
      'POST',
      '/agent/start',
      payload,
      options?.signal,
    );

    const workflowId = startResponse.workflowId as string;

    const handle: AgentHandle = {
      workflowId,
      correlationId,

      getStatus: () => this._getStatus(workflowId, options?.signal),

      wait: async (pollIntervalMs = 500) => {
        while (true) {
          const status = await this._getStatus(workflowId, options?.signal);
          if (TERMINAL_STATUSES.has(status.status)) {
            return makeAgentResult({
              output: status.output,
              workflowId,
              correlationId,
              status: status.status,
            });
          }
          await sleep(pollIntervalMs);
        }
      },

      respond: (output) => this._respond(workflowId, output, options?.signal),

      approve: (output?) =>
        this._respond(workflowId, { approved: true, ...output }, options?.signal),

      reject: (reason?) =>
        this._respond(workflowId, { approved: false, reason }, options?.signal),

      send: (message) =>
        this._respond(workflowId, { message }, options?.signal),

      pause: () =>
        this._httpRequest('PUT', `/workflow/${workflowId}/pause`, undefined, options?.signal).then(
          () => {},
        ),

      resume: () =>
        this._httpRequest('PUT', `/workflow/${workflowId}/resume`, undefined, options?.signal).then(
          () => {},
        ),

      cancel: () =>
        this._httpRequest(
          'DELETE',
          `/workflow/${workflowId}`,
          undefined,
          options?.signal,
        ).then(() => {}),

      stream: () => {
        const sseUrl = `${this.config.serverUrl}/agent/${workflowId}/sse`;
        return new AgentStream(
          sseUrl,
          this.authHeaders,
          workflowId,
          async (body) => this._respond(workflowId, body, options?.signal),
          this.config.serverUrl,
        );
      },
    };

    return handle;
  }

  // ── stream() ──────────────────────────────────────────

  /**
   * Start an agent and return a connected AgentStream.
   */
  async stream(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentStream> {
    const framework = detectFramework(agent);
    if (framework !== null) {
      throw new AgentspanError('Framework not yet implemented');
    }

    const payload = this.serializer.serialize(agent, prompt, {
      sessionId: options?.sessionId,
      media: options?.media,
      idempotencyKey: options?.idempotencyKey,
    });

    if (options?.timeoutSeconds !== undefined) {
      payload.timeoutSeconds = options.timeoutSeconds;
    }

    // Register workers
    await this._registerAllWorkers(agent);
    this.workerManager.startPolling();

    // Start agent
    const startResponse = await this._httpRequest(
      'POST',
      '/agent/start',
      payload,
      options?.signal,
    );

    const workflowId = startResponse.workflowId as string;
    const sseUrl = `${this.config.serverUrl}/agent/${workflowId}/sse`;

    return new AgentStream(
      sseUrl,
      this.authHeaders,
      workflowId,
      async (body) => this._respond(workflowId, body, options?.signal),
      this.config.serverUrl,
    );
  }

  // ── deploy() ──────────────────────────────────────────

  /**
   * Deploy an agent workflow definition.
   */
  async deploy(agent: Agent): Promise<DeploymentInfo> {
    const payload = this.serializer.serialize(agent);
    const response = await this._httpRequest('POST', '/agent/deploy', payload);
    return response as unknown as DeploymentInfo;
  }

  // ── plan() ────────────────────────────────────────────

  /**
   * Compile an agent to a workflow definition without executing.
   */
  async plan(agent: Agent): Promise<object> {
    const payload = this.serializer.serialize(agent);
    const response = await this._httpRequest('POST', '/agent/compile', payload);
    return response;
  }

  // ── serve() ───────────────────────────────────────────

  /**
   * Start worker polling and keep the process alive.
   */
  async serve(): Promise<void> {
    this.workerManager.startPolling();

    // Keep process alive until SIGINT/SIGTERM
    return new Promise<void>((resolve) => {
      const onSignal = () => {
        this.workerManager.stopPolling();
        resolve();
      };
      process.on('SIGINT', onSignal);
      process.on('SIGTERM', onSignal);
    });
  }

  // ── shutdown() ────────────────────────────────────────

  /**
   * Stop worker polling.
   */
  async shutdown(): Promise<void> {
    this.workerManager.stopPolling();
  }

  // ── Private helpers ───────────────────────────────────

  /**
   * Build auth headers from config.
   */
  private _buildAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};

    if (this.config.apiKey) {
      headers['Authorization'] = `Bearer ${this.config.apiKey}`;
    } else if (this.config.authKey && this.config.authSecret) {
      headers['X-Auth-Key'] = this.config.authKey;
      headers['X-Auth-Secret'] = this.config.authSecret;
    }

    return headers;
  }

  /**
   * Shared HTTP request wrapper with auth headers and error handling.
   */
  async _httpRequest(
    method: string,
    path: string,
    body?: unknown,
    signal?: AbortSignal,
  ): Promise<Record<string, unknown>> {
    const url = `${this.config.serverUrl}${path}`;

    const requestInit: RequestInit = {
      method,
      headers: {
        ...this.authHeaders,
        'Content-Type': 'application/json',
      },
    };

    if (body !== undefined) {
      requestInit.body = JSON.stringify(body);
    }

    if (signal) {
      requestInit.signal = signal;
    }

    const response = await fetch(url, requestInit);

    if (!response.ok) {
      const responseBody = await response.text();
      throw new AgentAPIError(
        `HTTP ${method} ${path} failed: ${response.status}`,
        response.status,
        responseBody,
      );
    }

    const text = await response.text();
    if (!text || text.trim() === '') return {};

    try {
      return JSON.parse(text);
    } catch {
      return { result: text };
    }
  }

  /**
   * Get agent status.
   */
  private async _getStatus(workflowId: string, signal?: AbortSignal): Promise<AgentStatus> {
    const response = await this._httpRequest(
      'GET',
      `/agent/${workflowId}/status`,
      undefined,
      signal,
    );
    return response as unknown as AgentStatus;
  }

  /**
   * Send a respond payload to a waiting agent.
   */
  private async _respond(workflowId: string, body: unknown, signal?: AbortSignal): Promise<void> {
    await this._httpRequest('POST', `/agent/${workflowId}/respond`, body, signal);
  }

  /**
   * Recursively collect all ToolDefs with handlers from an agent tree.
   */
  private _collectToolDefs(agent: Agent): ToolDef[] {
    const defs: ToolDef[] = [];

    for (const t of agent.tools) {
      try {
        const def = getToolDef(t);
        if (def.func != null) {
          defs.push(def);
        }
      } catch {
        // Skip unrecognized tool formats
      }
    }

    // Recurse into sub-agents
    for (const subAgent of agent.agents) {
      defs.push(...this._collectToolDefs(subAgent));
    }

    return defs;
  }

  /**
   * Register all tool workers for an agent tree.
   */
  private async _registerAllWorkers(agent: Agent): Promise<void> {
    const toolDefs = this._collectToolDefs(agent);

    for (const def of toolDefs) {
      const handler = def.func!;
      await this.workerManager.registerTaskDef(def.name, {
        timeoutSeconds: def.timeoutSeconds,
      });
      this.workerManager.addWorker(def.name, async (inputData) => {
        const toolContext = inputData['__toolContext__'];
        // Remove internal injection
        delete inputData['__toolContext__'];
        return handler(inputData, toolContext);
      });
    }
  }

  /**
   * Stub for framework execution — throws for now.
   */
  private async _runFramework(
    _agent: Agent,
    _prompt: string,
    _framework: unknown,
    _options?: RunOptions,
  ): Promise<AgentResult> {
    throw new AgentspanError('Framework not yet implemented');
  }
}

// ── Singleton functions ─────────────────────────────────

let _singletonRuntime: AgentRuntime | null = null;

function getRuntime(): AgentRuntime {
  if (!_singletonRuntime) {
    _singletonRuntime = new AgentRuntime();
  }
  return _singletonRuntime;
}

/**
 * Configure the singleton AgentRuntime.
 */
export function configure(options: AgentConfigOptions): AgentRuntime {
  _singletonRuntime = new AgentRuntime(options);
  return _singletonRuntime;
}

/**
 * Run an agent using the singleton runtime.
 */
export function run(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentResult> {
  return getRuntime().run(agent, prompt, options);
}

/**
 * Start an agent using the singleton runtime.
 */
export function start(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentHandle> {
  return getRuntime().start(agent, prompt, options);
}

/**
 * Stream an agent using the singleton runtime.
 */
export function stream(agent: Agent, prompt: string, options?: RunOptions): Promise<AgentStream> {
  return getRuntime().stream(agent, prompt, options);
}

/**
 * Deploy an agent using the singleton runtime.
 */
export function deploy(agent: Agent): Promise<DeploymentInfo> {
  return getRuntime().deploy(agent);
}

/**
 * Compile an agent to a workflow definition using the singleton runtime.
 */
export function plan(agent: Agent): Promise<object> {
  return getRuntime().plan(agent);
}

/**
 * Start the singleton runtime worker polling.
 */
export function serve(): Promise<void> {
  return getRuntime().serve();
}

/**
 * Stop the singleton runtime worker polling.
 */
export function shutdown(): Promise<void> {
  return getRuntime().shutdown();
}

// ── Helpers ─────────────────────────────────────────────

function generateCorrelationId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    // Fallback for environments without crypto.randomUUID
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
