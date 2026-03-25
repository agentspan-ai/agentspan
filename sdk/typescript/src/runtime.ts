import type {
  AgentResult,
  AgentEvent,
  AgentStatus,
  DeploymentInfo,
  RunOptions,
  ToolDef,
  GuardrailDef,
  FrameworkId,
} from './types.js';
import { AgentAPIError, AgentspanError } from './errors.js';
import { AgentConfig } from './config.js';
import type { AgentConfigOptions } from './config.js';
import { Agent } from './agent.js';
import type { CallbackHandler } from './agent.js';
import { AgentConfigSerializer } from './serializer.js';
import { getToolDef } from './tool.js';
import { WorkerManager } from './worker.js';
import { AgentStream } from './stream.js';
import { makeAgentResult } from './result.js';
import { TERMINAL_STATUSES } from './result.js';
import type { TerminationCondition } from './termination.js';
import { detectFramework } from './frameworks/detect.js';
import { serializeFrameworkAgent } from './frameworks/serializer.js';
import { serializeLangGraph } from './frameworks/langgraph-serializer.js';
import { serializeLangChain } from './frameworks/langchain-serializer.js';

/**
 * Callback method → wire position mapping (must match serializer.ts).
 */
const CALLBACK_POSITION_MAP: Record<string, string> = {
  onAgentStart: 'before_agent',
  onAgentEnd: 'after_agent',
  onModelStart: 'before_model',
  onModelEnd: 'after_model',
  onToolStart: 'before_tool',
  onToolEnd: 'after_tool',
};

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
   * Accepts native Agent instances or framework agent objects (Vercel AI, LangGraph, etc.).
   */
  async run(agent: Agent | object, prompt: string, options?: RunOptions): Promise<AgentResult> {
    const framework = detectFramework(agent);
    if (framework !== null) {
      return this._runFramework(agent, prompt, framework, options);
    }

    // Native Agent path — safe to cast since detectFramework returned null for non-Agent
    const nativeAgent = agent as Agent;
    const correlationId = generateCorrelationId();

    // Serialize agent config
    const payload = this.serializer.serialize(nativeAgent, prompt, {
      sessionId: options?.sessionId,
      media: options?.media,
      idempotencyKey: options?.idempotencyKey,
    });

    if (options?.timeoutSeconds !== undefined) {
      payload.timeoutSeconds = options.timeoutSeconds;
    }

    // Register workers for all tools
    await this._registerAllWorkers(nativeAgent);
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
      const sseUrl = `${this.config.serverUrl}/agent/stream/${workflowId}`;
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
   * Accepts native Agent instances or framework agent objects.
   */
  async start(agent: Agent | object, prompt: string, options?: RunOptions): Promise<AgentHandle> {
    const framework = detectFramework(agent);
    if (framework !== null) {
      return this._startFramework(agent, prompt, framework, options);
    }

    const nativeAgent = agent as Agent;
    const correlationId = generateCorrelationId();

    const payload = this.serializer.serialize(nativeAgent, prompt, {
      sessionId: options?.sessionId,
      media: options?.media,
      idempotencyKey: options?.idempotencyKey,
    });

    if (options?.timeoutSeconds !== undefined) {
      payload.timeoutSeconds = options.timeoutSeconds;
    }

    // Register workers
    await this._registerAllWorkers(nativeAgent);
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
        const sseUrl = `${this.config.serverUrl}/agent/stream/${workflowId}`;
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
   * Accepts native Agent instances or framework agent objects.
   */
  async stream(agent: Agent | object, prompt: string, options?: RunOptions): Promise<AgentStream> {
    const framework = detectFramework(agent);
    if (framework !== null) {
      throw new AgentspanError(
        'Framework streaming is not yet supported. Use run() for framework agents.',
      );
    }

    const nativeAgent = agent as Agent;
    const payload = this.serializer.serialize(nativeAgent, prompt, {
      sessionId: options?.sessionId,
      media: options?.media,
      idempotencyKey: options?.idempotencyKey,
    });

    if (options?.timeoutSeconds !== undefined) {
      payload.timeoutSeconds = options.timeoutSeconds;
    }

    // Register workers
    await this._registerAllWorkers(nativeAgent);
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
   * Register all workers for an agent tree: tools, termination, guardrails,
   * stopWhen, callbacks, gates, and router functions.
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

    // Register custom guardrail workers from tools
    for (const def of toolDefs) {
      if (def.guardrails) {
        for (const g of def.guardrails) {
          const gDef = this._normalizeGuardrailDef(g);
          if (gDef && gDef.func && gDef.taskName) {
            await this._registerGuardrailWorker(gDef);
          }
        }
      }
    }

    // Register system workers for the full agent tree
    await this._registerSystemWorkers(agent);
  }

  /**
   * Recursively register all system workers (non-tool) for an agent tree.
   */
  private async _registerSystemWorkers(agent: Agent): Promise<void> {
    // Termination
    if (agent.termination) {
      await this._registerTerminationWorker(agent.name, agent.termination as TerminationCondition);
    }

    // Custom guardrails (those with func)
    for (const g of agent.guardrails) {
      const gDef = this._normalizeGuardrailDef(g);
      if (gDef && gDef.func && gDef.taskName) {
        await this._registerGuardrailWorker(gDef);
      }
    }

    // stopWhen
    if (agent.stopWhen) {
      await this._registerStopWhenWorker(agent.name, agent.stopWhen);
    }

    // Callbacks
    if (agent.callbacks.length > 0) {
      await this._registerCallbackWorkers(agent.name, agent.callbacks);
    }

    // Gate (callable)
    if (agent.gate && typeof agent.gate.fn === 'function') {
      await this._registerGateWorker(agent.name, agent.gate.fn as (...args: unknown[]) => unknown);
    }

    // Router (function, not Agent)
    if (agent.router && typeof agent.router === 'function') {
      await this._registerRouterWorker(agent.name, agent.router as (...args: unknown[]) => string);
    }

    // Recurse into sub-agents
    for (const subAgent of agent.agents) {
      await this._registerSystemWorkers(subAgent);
    }
  }

  /**
   * Register a termination condition worker.
   * Server dispatches {agent}_termination with {result, iteration, messages}.
   * Worker returns {should_continue, reason}.
   */
  private async _registerTerminationWorker(
    agentName: string,
    cond: TerminationCondition,
  ): Promise<void> {
    const taskName = `${agentName}_termination`;
    await this.workerManager.registerTaskDef(taskName, { timeoutSeconds: 120 });
    this.workerManager.addWorker(taskName, async (inputData) => {
      const result = String(inputData['result'] ?? '');
      const iteration = Number(inputData['iteration'] ?? 0);
      const messages = Array.isArray(inputData['messages']) ? inputData['messages'] : [];
      try {
        const outcome = cond.shouldTerminate({ result, messages, iteration });
        return { should_continue: !outcome.shouldTerminate, reason: outcome.reason };
      } catch {
        return { should_continue: true, reason: '' };
      }
    });
  }

  /**
   * Register a custom guardrail worker.
   * Server dispatches {guardrail.taskName} with {content, iteration}.
   * Worker returns {passed, message, on_fail, ...}.
   */
  private async _registerGuardrailWorker(gDef: GuardrailDef): Promise<void> {
    const taskName = gDef.taskName!;
    const fn = gDef.func!;
    await this.workerManager.registerTaskDef(taskName, { timeoutSeconds: 120 });
    this.workerManager.addWorker(taskName, async (inputData) => {
      const content = String(inputData['content'] ?? '');
      try {
        const result = await fn(content);
        return {
          passed: result.passed ?? true,
          message: result.message ?? '',
          on_fail: gDef.onFail ?? 'raise',
          fixed_output: result.fixedOutput,
          guardrail_name: gDef.name,
          should_continue: result.passed ?? true,
        };
      } catch (err) {
        return {
          passed: false,
          message: err instanceof Error ? err.message : String(err),
          on_fail: gDef.onFail ?? 'raise',
          guardrail_name: gDef.name,
          should_continue: false,
        };
      }
    });
  }

  /**
   * Register a stopWhen callback worker.
   * Server dispatches {agent}_stop_when with {result, iteration}.
   * Worker returns {should_continue}.
   */
  private async _registerStopWhenWorker(
    agentName: string,
    stopWhenFn: (messages: unknown[], ...args: unknown[]) => boolean,
  ): Promise<void> {
    const taskName = `${agentName}_stop_when`;
    await this.workerManager.registerTaskDef(taskName, { timeoutSeconds: 120 });
    this.workerManager.addWorker(taskName, async (inputData) => {
      const result = String(inputData['result'] ?? '');
      const iteration = Number(inputData['iteration'] ?? 0);
      try {
        const shouldStop = stopWhenFn([result], iteration);
        return { should_continue: !shouldStop };
      } catch {
        return { should_continue: true };
      }
    });
  }

  /**
   * Register callback workers for each lifecycle position.
   * Server dispatches {agent}_{position} with {messages, llm_result}.
   * Worker returns the callback result or {}.
   */
  private async _registerCallbackWorkers(
    agentName: string,
    callbacks: CallbackHandler[],
  ): Promise<void> {
    for (const [methodName, wirePosition] of Object.entries(CALLBACK_POSITION_MAP)) {
      // Check if any handler implements this method
      const handlers = callbacks.filter(
        (h) => typeof (h as Record<string, unknown>)[methodName] === 'function',
      );
      if (handlers.length === 0) continue;

      const taskName = `${agentName}_${wirePosition}`;
      await this.workerManager.registerTaskDef(taskName, { timeoutSeconds: 120 });
      this.workerManager.addWorker(taskName, async (inputData) => {
        const messages = inputData['messages'] ?? null;
        const llmResult = inputData['llm_result'] ?? null;
        try {
          let result: unknown = {};
          for (const handler of handlers) {
            const fn = (handler as Record<string, unknown>)[methodName] as Function;
            // Pass server data matching CallbackHandler method signatures:
            // before/after_agent: (agentName, data)
            // before/after_model: (agentName, messages|response)
            // before/after_tool:  (agentName, toolName, data)
            const data = messages ?? llmResult;
            result = await fn.call(handler, agentName, data);
          }
          return typeof result === 'object' && result !== null ? result : {};
        } catch {
          return {};
        }
      });
    }
  }

  /**
   * Register a callable gate worker.
   * Server dispatches {agent}_gate with {result}.
   * Worker returns {decision: "continue"|"stop"}.
   */
  private async _registerGateWorker(
    agentName: string,
    gateFn: (...args: unknown[]) => unknown,
  ): Promise<void> {
    const taskName = `${agentName}_gate`;
    await this.workerManager.registerTaskDef(taskName, { timeoutSeconds: 120 });
    this.workerManager.addWorker(taskName, async (inputData) => {
      const result = String(inputData['result'] ?? '');
      try {
        const decision = await gateFn(result);
        if (typeof decision === 'string') {
          return { decision };
        }
        return { decision: decision ? 'continue' : 'stop' };
      } catch {
        return { decision: 'continue' };
      }
    });
  }

  /**
   * Register a function-based router worker.
   * Server dispatches {agent}_router_fn with {prompt}.
   * Worker returns {selected_agent}.
   */
  private async _registerRouterWorker(
    agentName: string,
    routerFn: (...args: unknown[]) => string,
  ): Promise<void> {
    const taskName = `${agentName}_router_fn`;
    await this.workerManager.registerTaskDef(taskName, { timeoutSeconds: 120 });
    this.workerManager.addWorker(taskName, async (inputData) => {
      const prompt = String(inputData['prompt'] ?? '');
      try {
        const selected = await routerFn(prompt);
        return { selected_agent: selected };
      } catch {
        return { selected_agent: '' };
      }
    });
  }

  /**
   * Normalize a guardrail from any input format to GuardrailDef (if it has a func).
   */
  private _normalizeGuardrailDef(g: unknown): GuardrailDef | null {
    if (g == null || typeof g !== 'object') return null;

    // Already a GuardrailDef with func
    const obj = g as Record<string, unknown>;
    if (typeof obj.func === 'function') {
      return obj as unknown as GuardrailDef;
    }

    // RegexGuardrail, LLMGuardrail — server-side, no local worker needed
    return null;
  }

  /**
   * Derive a worker name from a framework agent object.
   */
  private _deriveWorkerName(agent: object, frameworkId: FrameworkId): string {
    const a = agent as Record<string, unknown>;
    if (typeof a.id === 'string' && a.id.length > 0) return a.id;
    if (typeof a.name === 'string' && a.name.length > 0) return a.name;
    if (agent.constructor && agent.constructor.name !== 'Object') {
      return agent.constructor.name;
    }
    return `${frameworkId}_agent`;
  }

  /**
   * Serialize a framework agent into (rawConfig, workers) using extraction.
   */
  private _serializeFramework(agent: object, frameworkId: FrameworkId) {
    switch (frameworkId) {
      case 'langgraph':
        return serializeLangGraph(agent);
      case 'langchain':
        return serializeLangChain(agent);
      case 'openai':
      case 'google_adk':
        return serializeFrameworkAgent(agent);
      default:
        throw new AgentspanError(`Unsupported framework: ${frameworkId}`);
    }
  }

  /**
   * Run a framework agent via extraction.
   *
   * 1. Serialize the framework agent into rawConfig + WorkerInfo[]
   * 2. Register task definitions for each extracted worker
   * 3. Add workers to WorkerManager
   * 4. Start polling
   * 5. POST /agent/start with extracted rawConfig
   * 6. Wait for result via SSE stream
   */
  private async _runFramework(
    agent: object,
    prompt: string,
    frameworkId: FrameworkId,
    options?: RunOptions,
  ): Promise<AgentResult> {
    const correlationId = generateCorrelationId();
    const [rawConfig, workers] = this._serializeFramework(agent, frameworkId);

    // Register task definitions and add workers for each extracted tool
    for (const worker of workers) {
      await this.workerManager.registerTaskDef(worker.name, {
        timeoutSeconds: 600,
      });
      if (worker.func) {
        const fn = worker.func;
        this.workerManager.addWorker(worker.name, async (inputData) => {
          const cleanInput = { ...inputData };
          delete cleanInput['__workflowInstanceId__'];
          delete cleanInput['__toolContext__'];
          delete cleanInput['_agent_state'];
          delete cleanInput['method'];
          delete cleanInput['__agentspan_ctx__'];
          return fn(cleanInput);
        });
      }
    }

    this.workerManager.startPolling();

    try {
      // POST /agent/start with extracted config
      const startPayload = {
        framework: frameworkId,
        rawConfig,
        prompt,
        sessionId: options?.sessionId,
      };

      const startResponse = await this._httpRequest(
        'POST',
        '/agent/start',
        startPayload,
        options?.signal,
      );

      const workflowId = startResponse.workflowId as string;

      // Create SSE stream to drain events and wait for completion
      const sseUrl = `${this.config.serverUrl}/agent/stream/${workflowId}`;
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

      // Build result from stream
      const result = await agentStream.getResult();
      (result as unknown as Record<string, unknown>).correlationId = correlationId;

      return result;
    } finally {
      this.workerManager.stopPolling();
    }
  }

  /**
   * Start a framework agent asynchronously. Returns a handle for interaction.
   */
  private async _startFramework(
    agent: object,
    prompt: string,
    frameworkId: FrameworkId,
    options?: RunOptions,
  ): Promise<AgentHandle> {
    const correlationId = generateCorrelationId();
    const [rawConfig, workers] = this._serializeFramework(agent, frameworkId);

    // Register task definitions and add workers for each extracted tool
    for (const worker of workers) {
      await this.workerManager.registerTaskDef(worker.name, {
        timeoutSeconds: 600,
      });
      if (worker.func) {
        const fn = worker.func;
        this.workerManager.addWorker(worker.name, async (inputData) => {
          const cleanInput = { ...inputData };
          delete cleanInput['__workflowInstanceId__'];
          delete cleanInput['__toolContext__'];
          delete cleanInput['_agent_state'];
          delete cleanInput['method'];
          delete cleanInput['__agentspan_ctx__'];
          return fn(cleanInput);
        });
      }
    }

    this.workerManager.startPolling();

    // POST /agent/start with extracted config
    const startPayload = {
      framework: frameworkId,
      rawConfig,
      prompt,
      sessionId: options?.sessionId,
    };

    const startResponse = await this._httpRequest(
      'POST',
      '/agent/start',
      startPayload,
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
        const sseUrl = `${this.config.serverUrl}/agent/stream/${workflowId}`;
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
 * Accepts native Agent instances or framework agent objects.
 */
export function run(agent: Agent | object, prompt: string, options?: RunOptions): Promise<AgentResult> {
  return getRuntime().run(agent, prompt, options);
}

/**
 * Start an agent using the singleton runtime.
 * Accepts native Agent instances or framework agent objects.
 */
export function start(agent: Agent | object, prompt: string, options?: RunOptions): Promise<AgentHandle> {
  return getRuntime().start(agent, prompt, options);
}

/**
 * Stream an agent using the singleton runtime.
 * Accepts native Agent instances or framework agent objects.
 */
export function stream(agent: Agent | object, prompt: string, options?: RunOptions): Promise<AgentStream> {
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
