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
import { OnToolResult, OnTextMention, OnCondition } from './handoff.js';
import type { HandoffContext } from './handoff.js';
import { detectFramework } from './frameworks/detect.js';
import { serializeFrameworkAgent } from './frameworks/serializer.js';
import { serializeLangGraph } from './frameworks/langgraph-serializer.js';
import { serializeLangChain } from './frameworks/langchain-serializer.js';
import { createSkillWorkers } from './skill.js';

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
  readonly executionId: string;
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
    if (options?.credentials) {
      payload.credentials = options.credentials;
    }

    // Register tool workers (always needed) before calling the server
    await this._registerToolWorkers(nativeAgent);

    // Start agent — response may include requiredWorkers
    const startResponse = await this._httpRequest(
      'POST',
      '/agent/start',
      payload,
      options?.signal,
    );

    const executionId = startResponse.executionId as string;
    const requiredWorkers = this._parseRequiredWorkers(startResponse);

    // Register system workers filtered by server-provided list
    await this._registerSystemWorkers(nativeAgent, requiredWorkers);
    this.workerManager.startPolling();

    try {
      // Create SSE stream
      const sseUrl = `${this.config.serverUrl}/agent/stream/${executionId}`;
      const agentStream = new AgentStream(
        sseUrl,
        this.authHeaders,
        executionId,
        async (body) => this._respond(executionId, body, options?.signal),
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
        const status = await this._getStatus(executionId, options?.signal);
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
    if (options?.credentials) {
      payload.credentials = options.credentials;
    }

    // Register tool workers (always needed) before calling the server
    await this._registerToolWorkers(nativeAgent);

    // Start agent — response may include requiredWorkers
    const startResponse = await this._httpRequest(
      'POST',
      '/agent/start',
      payload,
      options?.signal,
    );

    const executionId = startResponse.executionId as string;
    const requiredWorkers = this._parseRequiredWorkers(startResponse);

    // Register system workers filtered by server-provided list
    await this._registerSystemWorkers(nativeAgent, requiredWorkers);
    this.workerManager.startPolling();

    const handle: AgentHandle = {
      executionId,
      correlationId,

      getStatus: () => this._getStatus(executionId, options?.signal),

      wait: async (pollIntervalMs = 500) => {
        while (true) {
          const status = await this._getStatus(executionId, options?.signal);
          if (TERMINAL_STATUSES.has(status.status)) {
            return makeAgentResult({
              output: status.output,
              executionId,
              correlationId,
              status: status.status,
            });
          }
          await sleep(pollIntervalMs);
        }
      },

      respond: (output) => this._respond(executionId, output, options?.signal),

      approve: (output?) =>
        this._respond(executionId, { approved: true, ...output }, options?.signal),

      reject: (reason?) =>
        this._respond(executionId, { approved: false, reason }, options?.signal),

      send: (message) =>
        this._respond(executionId, { message }, options?.signal),

      pause: () =>
        this._httpRequest('PUT', `/agent/${executionId}/pause`, undefined, options?.signal).then(
          () => {},
        ),

      resume: () =>
        this._httpRequest('PUT', `/agent/${executionId}/resume`, undefined, options?.signal).then(
          () => {},
        ),

      cancel: () =>
        this._httpRequest(
          'DELETE',
          `/agent/${executionId}/cancel`,
          undefined,
          options?.signal,
        ).then(() => {}),

      stream: () => {
        const sseUrl = `${this.config.serverUrl}/agent/stream/${executionId}`;
        return new AgentStream(
          sseUrl,
          this.authHeaders,
          executionId,
          async (body) => this._respond(executionId, body, options?.signal),
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
    const handle = await this.start(agent, prompt, options);
    return handle.stream();
  }

  // ── deploy() ──────────────────────────────────────────

  /**
   * Deploy an agent workflow definition.
   * Accepts native Agent instances or framework agent objects.
   */
  async deploy(agent: Agent | object): Promise<DeploymentInfo> {
    const framework = detectFramework(agent);

    let payload: Record<string, unknown>;
    if (framework !== null) {
      const [rawConfig] = this._serializeFramework(agent, framework);
      payload = { framework, rawConfig };
    } else {
      payload = this.serializer.serialize(agent as Agent);
    }

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
  private async _getStatus(executionId: string, signal?: AbortSignal): Promise<AgentStatus> {
    const response = await this._httpRequest(
      'GET',
      `/agent/${executionId}/status`,
      undefined,
      signal,
    );
    return response as unknown as AgentStatus;
  }

  /**
   * Send a respond payload to a waiting agent.
   */
  private async _respond(executionId: string, body: unknown, signal?: AbortSignal): Promise<void> {
    await this._httpRequest('POST', `/agent/${executionId}/respond`, body, signal);
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
   * Parse the requiredWorkers list from a server response.
   * Returns a Set<string> if present, or null for fallback (older servers).
   */
  private _parseRequiredWorkers(
    response: Record<string, unknown>,
  ): Set<string> | null {
    const raw = response.requiredWorkers;
    if (Array.isArray(raw)) {
      return new Set(raw.map(String));
    }
    return null;
  }

  /**
   * Register tool workers (user-defined) for an agent tree.
   * These are always registered regardless of requiredWorkers.
   */
  private async _registerToolWorkers(agent: Agent): Promise<void> {
    const toolDefs = this._collectToolDefs(agent);

    for (const def of toolDefs) {
      const handler = def.func!;
      // Extract credential names (string only; CredentialFile handled at serialization)
      const credNames = def.credentials
        ?.filter((c): c is string => typeof c === 'string')
        ?? undefined;
      this.workerManager.addWorker(def.name, async (inputData) => {
        const toolContext = inputData['__toolContext__'];
        // Remove internal injection
        delete inputData['__toolContext__'];
        return handler(inputData, toolContext);
      }, credNames);
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
  }

  /**
   * Recursively register all system workers (non-tool) for an agent tree.
   * When requiredWorkers is provided, only register workers whose task names
   * appear in the set. When null/undefined, register all (fallback for older servers).
   */
  private async _registerSystemWorkers(
    agent: Agent,
    requiredWorkers?: Set<string> | null,
  ): Promise<void> {
    // Helper: check if a task name is needed (always true when requiredWorkers is absent)
    const isNeeded = (taskName: string): boolean =>
      requiredWorkers == null || requiredWorkers.has(taskName);

    // Termination
    if (agent.termination) {
      const taskName = `${agent.name}_termination`;
      if (isNeeded(taskName)) {
        await this._registerTerminationWorker(agent.name, agent.termination as TerminationCondition);
      }
    }

    // Custom guardrails (those with func)
    for (const g of agent.guardrails) {
      const gDef = this._normalizeGuardrailDef(g);
      if (gDef && gDef.func && gDef.taskName) {
        if (isNeeded(gDef.taskName)) {
          await this._registerGuardrailWorker(gDef);
        }
      }
    }

    // stopWhen
    if (agent.stopWhen) {
      const taskName = `${agent.name}_stop_when`;
      if (isNeeded(taskName)) {
        await this._registerStopWhenWorker(agent.name, agent.stopWhen);
      }
    }

    // Callbacks
    if (agent.callbacks.length > 0) {
      // Callbacks produce multiple task names ({agent}_{position}), register if any are needed
      const callbackTaskNames = Object.values(CALLBACK_POSITION_MAP).map(
        (pos) => `${agent.name}_${pos}`,
      );
      const anyCallbackNeeded =
        requiredWorkers == null || callbackTaskNames.some((t) => requiredWorkers.has(t));
      if (anyCallbackNeeded) {
        await this._registerCallbackWorkers(agent.name, agent.callbacks, requiredWorkers);
      }
    }

    // Gate (callable)
    if (agent.gate && typeof agent.gate.fn === 'function') {
      const taskName = `${agent.name}_gate`;
      if (isNeeded(taskName)) {
        await this._registerGateWorker(agent.name, agent.gate.fn as (...args: unknown[]) => unknown);
      }
    }

    // Router (function, not Agent)
    if (agent.router && typeof agent.router === 'function') {
      const taskName = `${agent.name}_router_fn`;
      if (isNeeded(taskName)) {
        await this._registerRouterWorker(agent.name, agent.router as (...args: unknown[]) => string);
      }
    }

    // Swarm transfer workers (transfer_to_{peer} for each agent pair)
    if (agent.agents.length > 0) {
      // Register transfer workers if any transfer task is needed
      const allNames = [agent.name, ...agent.agents.map((a) => a.name)];
      const anyTransferNeeded =
        requiredWorkers == null ||
        allNames.some((src) =>
          allNames.some((dst) => src !== dst && requiredWorkers.has(`${src}_transfer_to_${dst}`)),
        );
      if (anyTransferNeeded) {
        await this._registerSwarmTransferWorkers(agent, requiredWorkers);
      }
    }

    // Check transfer worker (detects _transfer_to_ in tool_calls)
    {
      const taskName = `${agent.name}_check_transfer`;
      if (isNeeded(taskName)) {
        await this._registerCheckTransferWorker(agent.name);
      }
    }

    // Handoff check worker (swarm handoff detection)
    if (agent.handoffs.length > 0 || agent.strategy === 'swarm') {
      const taskName = `${agent.name}_handoff_check`;
      if (isNeeded(taskName)) {
        await this._registerHandoffCheckWorker(agent);
      }
    }

    // Process selection worker (manual strategy)
    if (agent.strategy === 'manual' && agent.agents.length > 0) {
      const taskName = `${agent.name}_process_selection`;
      if (isNeeded(taskName)) {
        await this._registerProcessSelectionWorker(agent);
      }
    }

    // Recurse into sub-agents
    for (const subAgent of agent.agents) {
      await this._registerSystemWorkers(subAgent, requiredWorkers);
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
    requiredWorkers?: Set<string> | null,
  ): Promise<void> {
    for (const [methodName, wirePosition] of Object.entries(CALLBACK_POSITION_MAP)) {
      // Check if any handler implements this method
      const handlers = callbacks.filter(
        (h) => typeof (h as Record<string, unknown>)[methodName] === 'function',
      );
      if (handlers.length === 0) continue;

      const taskName = `${agentName}_${wirePosition}`;
      if (requiredWorkers != null && !requiredWorkers.has(taskName)) continue;
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
   * Register transfer_to_{peer} workers for swarm agents.
   *
   * Each agent in the swarm gets transfer tools for its peers.
   * The transfer tools are no-ops — the actual handoff is detected
   * by check_transfer which inspects toolCalls output.
   *
   * When allowed_transitions is set, transfers to targets that no
   * agent is allowed to reach return an error message so the LLM
   * knows to try a different tool.
   */
  private async _registerSwarmTransferWorkers(
    agent: Agent,
    requiredWorkers?: Set<string> | null,
  ): Promise<void> {
    // Build set of all valid transfer targets from allowed_transitions
    const allowed = agent.allowedTransitions;
    const validTargets = new Set<string>();
    if (allowed) {
      for (const targets of Object.values(allowed)) {
        for (const t of targets) {
          validTargets.add(t);
        }
      }
    }

    const allNames = [agent.name, ...agent.agents.map((a) => a.name)];
    const registered = new Set<string>();

    for (const sourceName of allNames) {
      for (const peerName of allNames) {
        if (peerName === sourceName) continue;

        // Prefix with the SOURCE agent name (the one calling transfer)
        const toolName = `${sourceName}_transfer_to_${peerName}`;
        if (registered.has(toolName)) continue;
        registered.add(toolName);

        // Skip if server told us this worker is not needed
        if (requiredWorkers != null && !requiredWorkers.has(toolName)) continue;

        // If this target is never reachable via allowed_transitions,
        // return an error message so the LLM knows to stop trying.
        const isUnreachable = !!allowed && !validTargets.has(peerName);

        if (isUnreachable) {
          this.workerManager.addWorker(toolName, async () => ({
            result: `ERROR: ${toolName} is not available. Use a different transfer tool, or if you are done, just provide your final response without calling any transfer tool.`,
          }));
        } else {
          this.workerManager.addWorker(toolName, async () => ({}));
        }
      }
    }
  }

  /**
   * Register a check_transfer worker for hybrid handoff agents.
   * Server dispatches {agent}_check_transfer with {tool_calls}.
   * Worker scans for _transfer_to_ in tool call names.
   * Returns {is_transfer, transfer_to}.
   */
  private async _registerCheckTransferWorker(agentName: string): Promise<void> {
    const taskName = `${agentName}_check_transfer`;
    this.workerManager.addWorker(taskName, async (inputData) => {
      const toolCalls = Array.isArray(inputData['tool_calls']) ? inputData['tool_calls'] : [];
      for (const tc of toolCalls) {
        const name = typeof tc === 'object' && tc !== null ? String((tc as Record<string, unknown>).name ?? '') : '';
        if (name.includes('_transfer_to_')) {
          return { is_transfer: true, transfer_to: name.split('_transfer_to_')[1] };
        }
      }
      return { is_transfer: false, transfer_to: '' };
    });
  }

  /**
   * Register a handoff_check worker for swarm strategy.
   *
   * Supports dual-mechanism handoffs:
   * 1. Primary: Transfer tool detected (is_transfer=true, transfer_to=<name>)
   * 2. Secondary: Condition-based handoffs (OnTextMention, OnCondition, etc.)
   */
  private async _registerHandoffCheckWorker(agent: Agent): Promise<void> {
    const taskName = `${agent.name}_handoff_check`;
    const handoffConditions = agent.handoffs;

    // Parent agent is "0", sub-agents are "1", "2", ...
    const nameToIdx: Record<string, string> = { [agent.name]: '0' };
    agent.agents.forEach((sub, i) => {
      nameToIdx[sub.name] = String(i + 1);
    });
    const idxToName: Record<string, string> = {};
    for (const [name, idx] of Object.entries(nameToIdx)) {
      idxToName[idx] = name;
    }

    const allowed = agent.allowedTransitions;
    const maxBlockedRetries = 3;
    const blockedCounts: Record<string, number> = {};

    const isTransferTruthy = (val: unknown): boolean => {
      if (val === true) return true;
      if (typeof val === 'string') return val.trim().toLowerCase() === 'true';
      return false;
    };

    const isAllowed = (sourceIdx: string, targetName: string): boolean => {
      if (!allowed) return true;
      const sourceName = idxToName[sourceIdx] ?? '';
      return (allowed[sourceName] ?? []).includes(targetName);
    };

    this.workerManager.addWorker(taskName, async (inputData) => {
      const result = String(inputData['result'] ?? '');
      const activeAgent = String(inputData['active_agent'] ?? '0');
      const conversation = String(inputData['conversation'] ?? '');
      const isTransfer = inputData['is_transfer'];
      const transferTo = String(inputData['transfer_to'] ?? '');

      // Priority 1: Transfer tool detected
      if (isTransferTruthy(isTransfer)) {
        if (isAllowed(activeAgent, transferTo)) {
          delete blockedCounts[activeAgent];
          const targetIdx = nameToIdx[transferTo] ?? activeAgent;
          if (targetIdx !== activeAgent) {
            return { active_agent: targetIdx, handoff: true };
          }
        } else if (allowed) {
          // Transfer blocked — give the agent a few retries to self-correct
          const count = (blockedCounts[activeAgent] ?? 0) + 1;
          blockedCounts[activeAgent] = count;
          if (count <= maxBlockedRetries) {
            return { active_agent: activeAgent, handoff: true };
          }
          // Max retries exceeded — exit the loop
          delete blockedCounts[activeAgent];
          return { active_agent: activeAgent, handoff: false };
        }
      }

      // Priority 2: Condition-based handoffs (fallback)
      const context: HandoffContext = {
        result,
        messages: conversation,
        toolName: '',
        toolResult: '',
      };
      for (const cond of handoffConditions) {
        // Check if the condition object supports shouldHandoff evaluation
        const condObj = cond as { target?: string; shouldHandoff?: (ctx: HandoffContext) => boolean };
        if (typeof condObj.shouldHandoff === 'function' && condObj.target) {
          if (condObj.shouldHandoff(context)) {
            if (isAllowed(activeAgent, condObj.target)) {
              const targetIdx = nameToIdx[condObj.target] ?? activeAgent;
              if (targetIdx !== activeAgent) {
                return { active_agent: targetIdx, handoff: true };
              }
            }
          }
        }
      }

      // Neither transfer nor condition matched — loop exits
      return { active_agent: activeAgent, handoff: false };
    });
  }

  /**
   * Register a process_selection worker for manual strategy.
   * Server dispatches {agent}_process_selection with {human_output}.
   * Worker maps agent name to index.
   * Returns {selected}.
   */
  private async _registerProcessSelectionWorker(agent: Agent): Promise<void> {
    const taskName = `${agent.name}_process_selection`;
    const nameToIdx: Record<string, string> = {};
    agent.agents.forEach((sub, i) => {
      nameToIdx[sub.name] = String(i);
    });

    this.workerManager.addWorker(taskName, async (inputData) => {
      const humanOutput = inputData['human_output'];
      if (humanOutput == null) {
        return { selected: '0' };
      }
      if (typeof humanOutput === 'object' && humanOutput !== null) {
        const obj = humanOutput as Record<string, unknown>;
        const selected = String(obj.selected ?? obj.agent ?? '0');
        if (selected in nameToIdx) {
          return { selected: nameToIdx[selected] };
        }
        return { selected };
      }
      return { selected: String(humanOutput) };
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
      case 'skill':
        return this._serializeSkill(agent as Agent);
      default:
        throw new AgentspanError(`Unsupported framework: ${frameworkId}`);
    }
  }

  /**
   * Serialize a skill-based agent for server-side normalization.
   * Returns (rawConfig, workers) matching the framework serialization interface.
   */
  private _serializeSkill(
    agent: Agent,
  ): [Record<string, unknown>, { name: string; func?: Function }[]] {
    const a = agent as unknown as Record<string, unknown>;
    const rawConfig = a._framework_config as Record<string, unknown>;
    const skillWorkers = createSkillWorkers(agent);

    const workers = skillWorkers.map((sw) => ({
      name: sw.name,
      func: (inputData: Record<string, unknown>) => {
        const command = (inputData.command as string) ?? '';
        return sw.func(command);
      },
    }));

    return [rawConfig, workers];
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

    // Add workers for each extracted tool
    for (const worker of workers) {
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
        credentials: options?.credentials,
      };

      const startResponse = await this._httpRequest(
        'POST',
        '/agent/start',
        startPayload,
        options?.signal,
      );

      const executionId = startResponse.executionId as string;

      // Create SSE stream to drain events and wait for completion
      const sseUrl = `${this.config.serverUrl}/agent/stream/${executionId}`;
      const agentStream = new AgentStream(
        sseUrl,
        this.authHeaders,
        executionId,
        async (body) => this._respond(executionId, body, options?.signal),
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

    // Add workers for each extracted tool
    for (const worker of workers) {
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
      credentials: options?.credentials,
    };

    const startResponse = await this._httpRequest(
      'POST',
      '/agent/start',
      startPayload,
      options?.signal,
    );

    const executionId = startResponse.executionId as string;

    const handle: AgentHandle = {
      executionId,
      correlationId,

      getStatus: () => this._getStatus(executionId, options?.signal),

      wait: async (pollIntervalMs = 500) => {
        while (true) {
          const status = await this._getStatus(executionId, options?.signal);
          if (TERMINAL_STATUSES.has(status.status)) {
            return makeAgentResult({
              output: status.output,
              executionId,
              correlationId,
              status: status.status,
            });
          }
          await sleep(pollIntervalMs);
        }
      },

      respond: (output) => this._respond(executionId, output, options?.signal),

      approve: (output?) =>
        this._respond(executionId, { approved: true, ...output }, options?.signal),

      reject: (reason?) =>
        this._respond(executionId, { approved: false, reason }, options?.signal),

      send: (message) =>
        this._respond(executionId, { message }, options?.signal),

      pause: () =>
        this._httpRequest('PUT', `/agent/${executionId}/pause`, undefined, options?.signal).then(
          () => {},
        ),

      resume: () =>
        this._httpRequest('PUT', `/agent/${executionId}/resume`, undefined, options?.signal).then(
          () => {},
        ),

      cancel: () =>
        this._httpRequest(
          'DELETE',
          `/agent/${executionId}/cancel`,
          undefined,
          options?.signal,
        ).then(() => {}),

      stream: () => {
        const sseUrl = `${this.config.serverUrl}/agent/stream/${executionId}`;
        return new AgentStream(
          sseUrl,
          this.authHeaders,
          executionId,
          async (body) => this._respond(executionId, body, options?.signal),
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
export function deploy(agent: Agent | object): Promise<DeploymentInfo> {
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
