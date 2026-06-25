// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * Control-plane client for the Agent Runtime API (`/agent/*`).
 *
 * Mirrors the Java/C#/Python SDK split: the `/agent/*` HTTP surface
 * (compile / deploy / start / status / respond / stream) lives here instead
 * of inline on {@link AgentRuntime}. On top of those raw endpoints it adds
 * agent-level convenience methods — {@link run}, {@link start}, {@link deploy},
 * {@link schedule} — and a {@link schedules} accessor for cron lifecycle.
 *
 * **Control-plane only.** {@link run} compiles + starts an agent and polls to
 * a result; it does NOT register or poll local tool workers. Agents that use
 * local `@tool` functions must run through {@link AgentRuntime}. For LLM-only
 * agents, remote tools (HTTP/MCP), or pre-deployed workflows, this is enough.
 *
 * Built on a lazily-memoized {@link ConductorClient}. The Conductor client is
 * what mints the Orkes JWT (via `tokenResource`); the raw `/agent/*` requests
 * carry that JWT as `X-Authorization` (see {@link _authHeaders}).
 */

import { createConductorClient } from "@io-orkes/conductor-javascript";
import type { AgentResult, AgentStatus, DeploymentInfo, RunOptions } from "./types.js";
import { AgentAPIError } from "./errors.js";
import { AgentConfig } from "./config.js";
import type { AgentConfigOptions } from "./config.js";
import { Agent } from "./agent.js";
import { AgentConfigSerializer } from "./serializer.js";
import { detectFramework } from "./frameworks/detect.js";
import { serializeFrameworkAgent } from "./frameworks/serializer.js";
import { serializeLangGraph } from "./frameworks/langgraph-serializer.js";
import { serializeLangChain } from "./frameworks/langchain-serializer.js";
import { Schedule, ScheduleClient } from "./schedule.js";
import type { SchedulerFetcher } from "./schedule.js";
import { WorkflowClient } from "./workflow-client.js";
import { makeAgentResult, TERMINAL_STATUSES } from "./result.js";
import { AgentStream } from "./stream.js";

/**
 * The resource client returned by `createConductorClient`. The package's
 * exported `ConductorClient` alias points at the bare `Client`, which lacks
 * the `*Resource` members, so we derive the real shape from the factory.
 */
export type ConductorClient = Awaited<ReturnType<typeof createConductorClient>>;

/** Handle to a control-plane-started agent (no local workers). */
export interface ClientHandle {
  readonly executionId: string;
  getStatus(): Promise<AgentStatus>;
  wait(pollIntervalMs?: number): Promise<AgentResult>;
  respond(output: unknown): Promise<void>;
  approve(output?: Record<string, unknown>): Promise<void>;
  reject(reason?: string): Promise<void>;
  send(message: string): Promise<void>;
  stream(): AgentStream;
}

/**
 * Decode the `exp` claim (epoch seconds) from a JWT. Returns 0 when the token
 * has no decodable expiry. Mirrors Python's `decode_jwt_exp`.
 */
export function decodeJwtExp(token: string): number {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return 0;
    let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4 !== 0) b64 += "=";
    const json = Buffer.from(b64, "base64").toString("utf-8");
    const claims = JSON.parse(json) as { exp?: number };
    return typeof claims.exp === "number" ? claims.exp : 0;
  } catch {
    return 0;
  }
}

export class AgentClient {
  readonly config: AgentConfig;

  private _clientPromise?: Promise<ConductorClient>;
  private _workflowClient?: WorkflowClient;
  private _scheduleClient?: ScheduleClient;
  private readonly serializer: AgentConfigSerializer;

  // Cached minted JWT (auth-key/secret path).
  private _token = "";
  private _tokenExp = 0; // epoch seconds; 0 == "no decodable expiry"

  constructor(options?: AgentConfigOptions | AgentConfig) {
    this.config = options instanceof AgentConfig ? options : new AgentConfig(options);
    this.serializer = new AgentConfigSerializer();
  }

  // ── Conductor client (lazy, memoized) ──────────────────────────────

  /**
   * Lazily create (once) and return the shared {@link ConductorClient}.
   * `createConductorClient` is async, so we memoize the promise.
   */
  getClient(): Promise<ConductorClient> {
    if (!this._clientPromise) {
      // Conductor SDK reads CONDUCTOR_SERVER_URL with priority; baseUrl is the
      // server root WITHOUT the trailing `/api` (agent endpoints add `/api`).
      const baseUrl = this.config.serverUrl.replace(/\/api\/?$/, "");
      this._clientPromise = createConductorClient({
        serverUrl: baseUrl,
        disableHttp2: true,
        keyId: this.config.authKey || undefined,
        keySecret: this.config.authSecret || undefined,
      });
    }
    return this._clientPromise;
  }

  /** Read-only workflow client over the shared Conductor client. */
  get workflows(): WorkflowClient {
    if (!this._workflowClient) {
      this._workflowClient = new WorkflowClient(
        () => this.getClient(),
        (executionId) => this.getExecution(executionId),
      );
    }
    return this._workflowClient;
  }

  /** Cron schedule lifecycle client (shares this client's HTTP plumbing). */
  get schedules(): ScheduleClient {
    if (!this._scheduleClient) {
      const fetcher: SchedulerFetcher = {
        request: (method, path, body) => this._rawRequestUntyped(method, path, body),
      };
      this._scheduleClient = new ScheduleClient(fetcher);
    }
    return this._scheduleClient;
  }

  // ── Auth ───────────────────────────────────────────────────────────

  /**
   * `X-Authorization` header for secured hosts (Orkes); `{}` when anonymous.
   *
   * Mirrors the Python SDK contract exactly:
   * - explicit `apiKey` is already a token → `X-Authorization: <apiKey>`
   * - else mint a JWT from `authKey`/`authSecret` (via the Conductor client's
   *   `tokenResource.generateToken`) and cache it until ~expiry
   * - no creds → no header
   */
  async _authHeaders(): Promise<Record<string, string>> {
    if (this.config.apiKey) {
      return { "X-Authorization": this.config.apiKey };
    }
    if (!this.config.authKey || !this.config.authSecret) {
      return {};
    }

    const now = Math.floor(Date.now() / 1000);
    if (this._token && (this._tokenExp === 0 || now < this._tokenExp - 30)) {
      return { "X-Authorization": this._token };
    }

    let token: string;
    try {
      const client = await this.getClient();
      const data = (await client.tokenResource.generateToken({
        keyId: this.config.authKey,
        keySecret: this.config.authSecret,
      })) as { token?: string } | undefined;
      token = data?.token ?? "";
    } catch {
      return {};
    }
    if (!token) return {};

    this._token = token;
    this._tokenExp = decodeJwtExp(token);
    return { "X-Authorization": token };
  }

  // ── Raw `/agent/*` HTTP (Agentspan-specific endpoints) ─────────────
  //
  // These endpoints are NOT part of the Conductor API surface, so they are
  // issued via raw `fetch` (the Conductor client only knows workflow/task/
  // scheduler/token resources). Auth is the minted Orkes JWT.

  /** Typed `/agent/*` request returning an object (or `{}` for empty bodies). */
  async _request(
    method: string,
    path: string,
    body?: unknown,
    signal?: AbortSignal,
  ): Promise<Record<string, unknown>> {
    const url = `${this.config.serverUrl}${path}`;
    const headers: Record<string, string> = {
      ...(await this._authHeaders()),
      "Content-Type": "application/json",
    };
    const requestInit: RequestInit = { method, headers };
    if (body !== undefined) requestInit.body = JSON.stringify(body);
    if (signal) requestInit.signal = signal;

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
    if (!text || text.trim() === "") return {};
    try {
      return JSON.parse(text);
    } catch {
      return { result: text };
    }
  }

  /** Untyped request (scheduler endpoints sometimes return arrays). */
  async _rawRequestUntyped(method: string, path: string, body?: unknown): Promise<unknown> {
    const url = `${this.config.serverUrl}${path}`;
    const headers: Record<string, string> = {
      ...(await this._authHeaders()),
      "Content-Type": "application/json",
    };
    const requestInit: RequestInit = { method, headers };
    if (body !== undefined) requestInit.body = JSON.stringify(body);
    const response = await fetch(url, requestInit);
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      const err = new Error(`HTTP ${response.status}: ${text || response.statusText}`) as Error & {
        status?: number;
        body?: string;
      };
      err.status = response.status;
      err.body = text;
      throw err;
    }
    const ct = response.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) {
      const t = await response.text();
      return t === "" ? null : t;
    }
    return response.json();
  }

  /** Auth headers for SSE/stream consumers that need the raw header map. */
  async authHeaders(): Promise<Record<string, string>> {
    return this._authHeaders();
  }

  // ── Low-level `/agent/*` endpoints ─────────────────────────────────

  /** POST /agent/start — start an agent execution. */
  async startAgent(payload: Record<string, unknown>, signal?: AbortSignal): Promise<Record<string, unknown>> {
    return this._request("POST", "/agent/start", payload, signal);
  }

  /** POST /agent/deploy — compile + register (no execution). */
  async deployAgent(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this._request("POST", "/agent/deploy", payload);
  }

  /** POST /agent/compile — compile agent config to a workflow def. */
  async compile(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this._request("POST", "/agent/compile", payload);
  }

  /** GET /agent/{id}/status — current execution status. */
  async status(executionId: string, signal?: AbortSignal): Promise<AgentStatus> {
    const r = await this._request("GET", `/agent/${executionId}/status`, undefined, signal);
    return r as unknown as AgentStatus;
  }

  /** POST /agent/{id}/respond — complete a pending human task. */
  async respond(executionId: string, body: unknown, signal?: AbortSignal): Promise<void> {
    await this._request("POST", `/agent/${executionId}/respond`, body, signal);
  }

  /** GET /agent/execution/{id} — full execution data (tasks, output, tokens). */
  async getExecution(executionId: string, signal?: AbortSignal): Promise<Record<string, unknown> | null> {
    try {
      return await this._request("GET", `/agent/execution/${executionId}`, undefined, signal);
    } catch {
      return null;
    }
  }

  /** A connected {@link AgentStream} for an execution's SSE feed. */
  async stream(executionId: string, signal?: AbortSignal): Promise<AgentStream> {
    const sseUrl = `${this.config.serverUrl}/agent/stream/${executionId}`;
    return new AgentStream(
      sseUrl,
      await this._authHeaders(),
      executionId,
      async (body) => this.respond(executionId, body, signal),
      this.config.serverUrl,
    );
  }

  // ── Agent-level convenience (control-plane only — NO local workers) ─

  /**
   * Compile + start an agent, then poll to an {@link AgentResult}.
   *
   * **Control-plane only** — does NOT register or poll local tool workers.
   * Use {@link AgentRuntime.run} for agents with local `@tool` functions.
   */
  async run(agent: Agent | object, prompt: string, opts?: RunOptions): Promise<AgentResult> {
    const handle = await this.start(agent, prompt, opts);
    return handle.wait();
  }

  /** Compile + start an agent; return a {@link ClientHandle}. No workers. */
  async start(agent: Agent | object, prompt: string, opts?: RunOptions): Promise<ClientHandle> {
    const framework = detectFramework(agent);
    let payload: Record<string, unknown>;
    if (framework !== null) {
      const [rawConfig] = this._serializeFramework(agent, framework);
      payload = { framework, rawConfig, prompt };
    } else {
      payload = this.serializer.serialize(agent as Agent, prompt, {
        sessionId: opts?.sessionId,
        media: opts?.media,
        idempotencyKey: opts?.idempotencyKey,
      });
    }
    if (opts?.timeoutSeconds !== undefined) payload.timeoutSeconds = opts.timeoutSeconds;
    if (opts?.credentials) payload.credentials = opts.credentials;
    if (opts?.context) payload.context = opts.context;
    if (opts?.plan !== undefined) {
      const { coercePlan } = await import("./plans.js");
      payload.static_plan = coercePlan(opts.plan as Parameters<typeof coercePlan>[0]);
    }

    const startResponse = await this.startAgent(payload, opts?.signal);
    const executionId = startResponse.executionId as string;
    return this._makeHandle(executionId, opts?.signal);
  }

  /** Compile + register one or more agents (no execution, no workers). */
  async deploy(...agents: (Agent | object)[]): Promise<DeploymentInfo[]> {
    if (agents.length === 0) throw new Error("deploy() requires at least one agent.");
    const results: DeploymentInfo[] = [];
    for (const agent of agents) {
      const framework = detectFramework(agent);
      let payload: Record<string, unknown>;
      if (framework !== null) {
        const [rawConfig] = this._serializeFramework(agent, framework);
        payload = { framework, rawConfig };
      } else {
        payload = this.serializer.serialize(agent as Agent);
      }
      const data = await this.deployAgent(payload);
      results.push(data as unknown as DeploymentInfo);
    }
    return results;
  }

  /**
   * Deploy *agent* and reconcile its cron *schedules* declaratively.
   *
   * Upserts the listed schedules and prunes the others; `[]` purges all;
   * `null`/`undefined` leaves them untouched. Reuses the {@link ScheduleClient}.
   */
  async schedule(
    agent: Agent | object,
    schedules: Schedule[] | null | undefined,
  ): Promise<DeploymentInfo> {
    const info = (await this.deploy(agent))[0];
    const agentName = (agent as Agent).name ?? info.agentName;
    if (!agentName) {
      throw new Error("schedule(...) requires the agent to have a name");
    }
    await this.schedules.reconcile(agentName, schedules);
    return info;
  }

  // ── Internal ───────────────────────────────────────────────────────

  private _serializeFramework(
    agent: object,
    framework: string,
  ): [Record<string, unknown>, unknown[]] {
    if (framework === "langgraph") return serializeLangGraph(agent);
    if (framework === "langchain") return serializeLangChain(agent);
    return serializeFrameworkAgent(agent);
  }

  private _makeHandle(executionId: string, signal?: AbortSignal): ClientHandle {
    return {
      executionId,
      getStatus: () => this.status(executionId, signal),
      respond: (output) => this.respond(executionId, output, signal),
      approve: (output) => this.respond(executionId, { approved: true, ...output }, signal),
      reject: (reason) => this.respond(executionId, { approved: false, reason }, signal),
      send: (message) => this.respond(executionId, { message }, signal),
      stream: () => {
        const sseUrl = `${this.config.serverUrl}/agent/stream/${executionId}`;
        return new AgentStream(
          sseUrl,
          {},
          executionId,
          async (body) => this.respond(executionId, body, signal),
          this.config.serverUrl,
        );
      },
      wait: async (pollIntervalMs = 500) => {
        for (;;) {
          const status = await this.status(executionId, signal);
          if (TERMINAL_STATUSES.has(status.status)) {
            const resultData: Parameters<typeof makeAgentResult>[0] = {
              output: status.output,
              executionId,
              status: status.status,
            };
            try {
              const tokenUsage = await this.workflows.extractTokenUsage(executionId);
              if (tokenUsage) resultData.tokenUsage = tokenUsage;
            } catch {
              // Non-critical.
            }
            return makeAgentResult(resultData);
          }
          await new Promise((r) => setTimeout(r, pollIntervalMs));
        }
      },
    };
  }
}
