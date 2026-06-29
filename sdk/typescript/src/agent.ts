import type { Strategy, CodeExecutionConfig, CliConfig, PrefillToolCall } from "./types.js";
import { agentTool } from "./tool.js";
import { ConfigurationError } from "./errors.js";
import { ClaudeCode } from "./claude-code.js";
import type { CliConfigOptions } from "./cli-config.js";
import { makeCliTool } from "./cli-config.js";
import { Context } from "./plans.js";

// ── Validation constants ──────────────────────────────────

/**
 * Valid agent name pattern: starts with a letter, followed by letters, digits,
 * underscores, or hyphens.
 */
const VALID_NAME_RE = /^[a-zA-Z][a-zA-Z0-9_-]*$/;

// ── PromptTemplate class ──────────────────────────────────

/**
 * Named prompt template with optional variable substitution.
 * References a server-managed prompt template.
 */
export class PromptTemplate {
  readonly name: string;
  readonly variables?: Record<string, string>;
  readonly version?: number;

  constructor(name: string, variables?: Record<string, string>, version?: number) {
    this.name = name;
    this.variables = variables;
    this.version = version;
  }
}

// ── AgentOptions ──────────────────────────────────────────

/**
 * Termination condition interface.
 * Implementations like TextMention, StopMessage, MaxMessage, TokenUsage
 * will be in termination.ts. For now we accept any object with toJSON().
 */
export interface TerminationCondition {
  toJSON(): object;
}

/**
 * Handoff condition interface.
 * Implementations will be in handoff.ts.
 */
export interface HandoffCondition {
  toJSON(): object;
}

/**
 * Gate condition interface.
 */
export interface GateCondition {
  toJSON?(): object;
  type?: string;
  text?: string;
  caseSensitive?: boolean;
  fn?: Function;
}

/**
 * Callback handler interface.
 */
export interface CallbackHandler {
  onAgentStart?(agentName: string, prompt: string): Promise<void>;
  onAgentEnd?(agentName: string, result: unknown): Promise<void>;
  onModelStart?(agentName: string, messages: unknown[]): Promise<void>;
  onModelEnd?(agentName: string, response: unknown): Promise<void>;
  onToolStart?(agentName: string, toolName: string, args: unknown): Promise<void>;
  onToolEnd?(agentName: string, toolName: string, result: unknown): Promise<void>;
}

/**
 * Memory interface for conversation history.
 */
export interface ConversationMemory {
  toChatMessages(): unknown[];
  maxMessages?: number;
}

/**
 * Options for constructing an Agent.
 */
export interface AgentOptions {
  name: string;
  model?: string | ClaudeCode;
  /** Custom base URL for the LLM provider (overrides env var defaults). */
  baseUrl?: string;
  instructions?: string | PromptTemplate | ((...args: unknown[]) => string);
  tools?: unknown[]; // Normalized via normalizeToolInput at serialization
  agents?: Agent[];
  strategy?: Strategy;
  router?: Agent | ((...args: unknown[]) => string);
  outputType?: unknown; // ZodSchema or JSON Schema object
  guardrails?: unknown[];
  memory?: ConversationMemory;
  maxTurns?: number;
  maxTokens?: number;
  /**
   * Reasoning effort for OpenAI reasoning models (e.g. "low", "medium",
   * "high"). Emitted as `reasoningEffort` on the wire to match Python/Java.
   */
  reasoningEffort?: string;
  /**
   * Token budget for proactive context-window condensation. When the running
   * context approaches this budget the server condenses history. Emitted as
   * `contextWindowBudget` to match Python/Java.
   */
  contextWindowBudget?: number;
  /**
   * Input/output field names to redact in execution history and the UI.
   * Maps to Conductor's `WorkflowDef.maskedFields`. NOTE: the server does
   * not yet apply this (known no-op); emitted for cross-SDK parity.
   */
  maskedFields?: string[];
  temperature?: number;
  timeoutSeconds?: number;
  external?: boolean;
  stopWhen?: (messages: unknown[], ...args: unknown[]) => boolean;
  termination?: TerminationCondition;
  handoffs?: HandoffCondition[];
  allowedTransitions?: Record<string, string[]>;
  introduction?: string;
  metadata?: Record<string, unknown>;
  callbacks?: CallbackHandler[];
  /**
   * Plan-first preamble (Google ADK feature). When true, the server augments
   * the system prompt with a "plan first, then execute" instruction. Not to
   * be confused with the {@link planner} sub-agent slot below — those serve
   * different purposes.
   */
  enablePlanning?: boolean;
  /**
   * PLAN_EXECUTE: the agent that produces the JSON plan. Required when
   * {@link strategy} is {@code "plan_execute"}. The planner can be a simple
   * agent or a multi-agent (e.g. SEQUENTIAL of explorer + planner).
   * Replaces the old positional {@code agents=[planner, fallback]} shape.
   */
  planner?: Agent;
  /**
   * PLAN_EXECUTE: the agent that runs agentically when the plan can't
   * compile or the compiled SUB_WORKFLOW fails at execution. Optional — if
   * absent, plan failures TERMINATE the workflow.
   */
  fallback?: Agent;
  includeContents?: "default" | "none";
  thinkingBudgetTokens?: number;
  requiredTools?: string[];
  /** Tool calls to execute before the first LLM turn. Results are injected into context. */
  prefillTools?: PrefillToolCall[];
  gate?: GateCondition;
  codeExecutionConfig?: CodeExecutionConfig;
  cliConfig?: CliConfig | CliConfigOptions;
  /** Shorthand: enable CLI command execution. */
  cliCommands?: boolean;
  /** Shorthand: allowed CLI commands (implies cliCommands=true). */
  cliAllowedCommands?: string[];
  credentials?: string[];
  /** Stateful execution — each run gets a unique domain UUID for worker isolation. */
  stateful?: boolean;
  /** Max LLM turns for the fallback agent in PLAN_EXECUTE strategy. */
  fallbackMaxTurns?: number;
  /**
   * Optional deterministic plan source for PLAN_EXECUTE strategy.
   * A SIMPLE task is called after the planner to read the plan from an
   * external source (e.g. contextbook). If the planner's text output fails
   * extraction, this fallback source is tried.
   * Format: { tool: "tool_name", args: { key: "value" } }.
   */
  planSource?: { tool: string; args?: Record<string, unknown> };
  /**
   * PLAN_EXECUTE planner context: a list of text snippets and/or URLs whose
   * contents are appended to the planner's user prompt as a
   * `## Reference Context` block on every planner invocation. URLs are
   * fetched dynamically — no compile-time fetch, no cache — so doc edits
   * go live without recompile.
   *
   * Bare strings auto-wrap to `Context(text=...)`. Use a {@link Context}
   * instance directly for URL entries (with optional credentialed
   * `headers`, `required`, `maxBytes`). Hand-rolled dicts in the wire
   * shape are also accepted for power users.
   *
   * Only valid with `strategy='plan_execute'`.
   */
  plannerContext?: (string | Context | Record<string, unknown>)[];
}

// ── Agent class ───────────────────────────────────────────

/**
 * The single orchestration primitive.
 * Every agent — simple or complex — is an instance of this class.
 */
export class Agent {
  readonly name: string;
  readonly model?: string;
  /** Custom base URL for the LLM provider (overrides env var defaults). */
  readonly baseUrl?: string;
  readonly instructions?: string | PromptTemplate | ((...args: unknown[]) => string);
  readonly tools: unknown[];
  readonly agents: Agent[];
  readonly strategy?: Strategy;
  readonly router?: Agent | ((...args: unknown[]) => string);
  readonly outputType?: unknown;
  readonly guardrails: unknown[];
  readonly memory?: ConversationMemory;
  readonly maxTurns: number;
  readonly maxTokens?: number;
  readonly reasoningEffort?: string;
  readonly contextWindowBudget?: number;
  readonly maskedFields?: string[];
  readonly temperature?: number;
  readonly timeoutSeconds: number;
  readonly external: boolean;
  readonly stateful: boolean;
  readonly stopWhen?: (messages: unknown[], ...args: unknown[]) => boolean;
  readonly termination?: TerminationCondition;
  readonly handoffs: HandoffCondition[];
  readonly allowedTransitions?: Record<string, string[]>;
  readonly introduction?: string;
  readonly metadata?: Record<string, unknown>;
  readonly callbacks: CallbackHandler[];
  readonly enablePlanning: boolean;
  /** PLAN_EXECUTE named slot (sub-agent that produces the JSON plan). */
  readonly planner?: Agent;
  /** PLAN_EXECUTE named slot (sub-agent that runs agentically on plan failure). */
  readonly fallback?: Agent;
  readonly includeContents?: "default" | "none";
  readonly thinkingBudgetTokens?: number;
  readonly requiredTools?: string[];
  readonly prefillTools?: PrefillToolCall[];
  readonly gate?: GateCondition;
  readonly codeExecutionConfig?: CodeExecutionConfig;
  readonly cliConfig?: CliConfig;
  readonly credentials?: string[];
  readonly fallbackMaxTurns?: number;
  readonly planSource?: { tool: string; args?: Record<string, unknown> };
  /**
   * Normalised planner-context entries — bare strings auto-wrapped to
   * `Context(text=...)`, raw dicts passed through. `undefined` when
   * the option wasn't supplied.
   */
  readonly plannerContext?: (Context | Record<string, unknown>)[];

  /** @internal Stored ClaudeCode config when model is ClaudeCode instance. */
  private readonly _claudeCodeConfig?: ClaudeCode;

  constructor(options: AgentOptions) {
    // ── Name validation ───────────────────────────────────
    if (!VALID_NAME_RE.test(options.name)) {
      throw new ConfigurationError(
        `Invalid agent name '${options.name}'. ` +
          `Names must start with a letter and contain only letters, digits, underscores, or hyphens.`,
      );
    }

    this.name = options.name;

    // Handle ClaudeCode config object
    if (options.model instanceof ClaudeCode) {
      this._claudeCodeConfig = options.model;
      this.model = options.model.toModelString();
    } else {
      this.model = options.model;
    }

    this.baseUrl = options.baseUrl;
    this.instructions = options.instructions;
    this.tools = [...(options.tools ?? [])];
    this.agents = options.agents ?? [];
    this.strategy = options.strategy;
    this.router = options.router;
    this.outputType = options.outputType;
    this.guardrails = options.guardrails ?? [];
    this.memory = options.memory;
    this.maxTurns = options.maxTurns ?? 25;
    this.maxTokens = options.maxTokens;
    this.reasoningEffort = options.reasoningEffort;
    this.contextWindowBudget = options.contextWindowBudget;
    this.maskedFields = options.maskedFields;
    this.temperature = options.temperature;
    this.timeoutSeconds = options.timeoutSeconds ?? 0;
    this.external = options.external ?? false;
    this.stateful = options.stateful ?? false;
    this.stopWhen = options.stopWhen;
    this.termination = options.termination;
    this.handoffs = options.handoffs ?? [];
    this.allowedTransitions = options.allowedTransitions;
    this.introduction = options.introduction;
    this.metadata = options.metadata;
    this.callbacks = options.callbacks ?? [];
    this.enablePlanning = options.enablePlanning ?? false;
    this.planner = options.planner;
    this.fallback = options.fallback;
    // ── PLAN_EXECUTE named-slot validation ────────────────
    // Named slots (planner=, fallback=) only valid with strategy=plan_execute;
    // passing them elsewhere would either NPE deep in a strategy compiler or
    // be silently ignored. Reject at construction with a clear message.
    if ((this.planner !== undefined || this.fallback !== undefined)
        && this.strategy !== "plan_execute") {
      throw new ConfigurationError(
        `Named slots 'planner' and 'fallback' are only valid with strategy='plan_execute'. ` +
          `Got strategy=${this.strategy ?? "<undefined>"}. ` +
          `Either set strategy='plan_execute' or pass sub-agents via agents=[...] instead.`,
      );
    }
    if (this.strategy === "plan_execute") {
      if (this.planner === undefined) {
        if (this.agents.length > 0) {
          throw new ConfigurationError(
            `strategy='plan_execute' no longer accepts agents=[planner, fallback]. ` +
              `Use the named slots: planner=<Agent> (required) and fallback=<Agent> (optional).`,
          );
        }
        throw new ConfigurationError(
          `strategy='plan_execute' requires planner=<Agent> (the agent that produces the JSON plan).`,
        );
      }
    }
    this.includeContents = options.includeContents;
    this.thinkingBudgetTokens = options.thinkingBudgetTokens;
    this.requiredTools = options.requiredTools;
    this.prefillTools = options.prefillTools;
    this.gate = options.gate;
    this.codeExecutionConfig = options.codeExecutionConfig;
    this.credentials = options.credentials;
    this.fallbackMaxTurns = options.fallbackMaxTurns;
    this.planSource = options.planSource;

    // ── plannerContext normalisation + validation ─────────
    // Bare strings auto-wrap to Context(text=...); Context instances and
    // raw dicts pass through. Rejected for non-PLAN_EXECUTE strategies
    // with a clear message (matches the planner=/fallback= guard).
    if (options.plannerContext !== undefined) {
      if (this.strategy !== "plan_execute") {
        throw new ConfigurationError(
          `'plannerContext' is only valid with strategy='plan_execute'. ` +
            `Got strategy=${this.strategy ?? "<undefined>"}. ` +
            `The context block is appended to the planner's user prompt at ` +
            `runtime, which only exists in PLAN_EXECUTE.`,
        );
      }
      const normalised: (Context | Record<string, unknown>)[] = [];
      options.plannerContext.forEach((entry, i) => {
        if (entry instanceof Context) {
          normalised.push(entry);
        } else if (typeof entry === "string") {
          normalised.push(new Context({ text: entry }));
        } else if (entry !== null && typeof entry === "object") {
          // Hand-rolled wire-shape dicts (matches how planSource is typed).
          normalised.push(entry as Record<string, unknown>);
        } else {
          throw new ConfigurationError(
            `plannerContext[${i}]: must be a Context, a string, or a dict; ` +
              `got ${typeof entry}`,
          );
        }
      });
      this.plannerContext = normalised;
    }

    // ── Duplicate sub-agent name detection ────────────────
    if (this.agents.length > 0) {
      const names = new Set<string>();
      for (const sub of this.agents) {
        if (names.has(sub.name)) {
          throw new ConfigurationError(
            `Duplicate sub-agent name '${sub.name}' in agent '${this.name}'. ` +
              `All sub-agent names must be unique.`,
          );
        }
        names.add(sub.name);
      }
    }

    // ── Strategy validation ───────────────────────────────
    if (this.strategy === "router" && !this.router) {
      throw new ConfigurationError(
        `Agent '${this.name}' uses strategy='router' but no 'router' parameter was provided. ` +
          `Provide an Agent or function as the router.`,
      );
    }

    // Validate claude-code tools are all strings
    if (this.isClaudeCode && this.tools.length > 0) {
      for (const t of this.tools) {
        if (typeof t !== "string") {
          throw new Error(
            `Claude Code agent '${this.name}' tools must be strings ` +
              `(e.g. 'Read', 'Edit', 'Bash'), got ${typeof t}`,
          );
        }
      }
    }

    // CLI command execution setup
    if (options.cliConfig != null) {
      // Could be a CliConfig (wire format from types.ts) or CliConfigOptions
      // Both have the same shape, so assign as wire format
      this.cliConfig = options.cliConfig as CliConfig;
    } else if (options.cliCommands || options.cliAllowedCommands) {
      this.cliConfig = {
        enabled: true,
        allowedCommands: options.cliAllowedCommands ?? [],
        timeout: 30,
        allowShell: false,
      };
    }

    // Auto-attach CLI tool when enabled
    if (this.cliConfig && this.cliConfig.enabled !== false) {
      const cliTool = makeCliTool(
        {
          allowedCommands: this.cliConfig.allowedCommands,
          timeout: this.cliConfig.timeout,
          allowShell: this.cliConfig.allowShell,
        },
        this.name,
      );
      this.tools.push(cliTool);
    }
  }

  // ── Claude Code detection ───────────────────────────────

  /**
   * True if this agent uses the Claude Agent SDK runtime.
   */
  get isClaudeCode(): boolean {
    return typeof this.model === "string" && this.model.startsWith("claude-code");
  }

  /**
   * The ClaudeCode config object, if this agent was created with one.
   */
  get claudeCodeConfig(): ClaudeCode | undefined {
    return this._claudeCodeConfig;
  }

  /**
   * Create a sequential pipeline: `a.pipe(b)`.
   *
   * FLATTENING RULE (base spec §14.14):
   * If `this` already has `strategy === 'sequential'`, merge agents arrays.
   * `a.pipe(b).pipe(c)` → Agent with agents: [a, b, c], NOT nested.
   */
  pipe(other: Agent): Agent {
    if (this.strategy === "sequential" && this.agents.length > 0) {
      // Flatten: merge other into existing sequential pipeline
      return new Agent({
        name: [...this.agents, other].map((a) => a.name).join("_"),
        model: this.model,
        agents: [...this.agents, other],
        strategy: "sequential",
      });
    }

    // Create new sequential pipeline
    return new Agent({
      name: `${this.name}_${other.name}`,
      model: this.model,
      agents: [this, other],
      strategy: "sequential",
    });
  }
}

// ── scatterGather ─────────────────────────────────────────

export interface ScatterGatherOptions {
  name: string;
  model?: string;
  instructions?: string;
  /** The worker agent that handles each sub-task. */
  workers: Agent[];
  /** Extra tools for the coordinator (in addition to the worker tools). */
  tools?: unknown[];
  /** Retries per sub-task on failure (default 2). */
  retryCount?: number;
  /** Base delay between retries in seconds (default 2). */
  retryDelaySeconds?: number;
  /** When true, a single sub-task failure fails the entire scatter-gather. Default false. */
  failFast?: boolean;
  /** Timeout in seconds for the entire coordinator (default 300). */
  timeoutSeconds?: number;
  /** @deprecated Use `instructions` instead. */
  coordinatorInstructions?: string;
}

const SCATTER_GATHER_PREFIX = (workerNames: string) =>
  `You are a coordinator that decomposes problems into independent sub-tasks.

WORKFLOW:
1. Analyze the input and identify independent sub-problems
2. Call the worker tool(s) MULTIPLE TIMES IN PARALLEL — once per sub-problem, each with a clear, self-contained prompt
3. After all results return, synthesize them into a unified answer

Available worker tools: ${workerNames}

IMPORTANT: Issue all tool calls in a SINGLE response to maximize parallelism.
`;

/**
 * Create a coordinator agent pre-configured for the scatter-gather pattern.
 *
 * The coordinator decomposes a problem into N independent sub-tasks,
 * dispatches the worker agent(s) N times in parallel (via `agentTool`),
 * and synthesizes the results. N is determined at runtime by the LLM.
 *
 * Each sub-task is a durable Conductor sub-workflow with automatic retries.
 */
export function scatterGather(options: ScatterGatherOptions): Agent {
  const workerTools = options.workers.map((worker) =>
    agentTool(worker, {
      retryCount: options.retryCount,
      retryDelaySeconds: options.retryDelaySeconds,
      optional: options.failFast === true ? false : true,
    }),
  );

  const resolvedModel = options.model ?? options.workers[0]?.model ?? "openai/gpt-4o";
  const workerNames = options.workers.map((w) => w.name).join(", ");
  const prefix = SCATTER_GATHER_PREFIX(workerNames);
  const userInstructions = options.instructions ?? options.coordinatorInstructions ?? "";
  const fullInstructions = userInstructions ? `${prefix}\n${userInstructions}` : prefix;

  const allTools = [...workerTools, ...(options.tools ?? [])];

  return new Agent({
    name: options.name,
    model: resolvedModel,
    instructions: fullInstructions,
    tools: allTools,
    timeoutSeconds: options.timeoutSeconds ?? 300,
  });
}

// ── @AgentDec decorator ───────────────────────────────────

const AGENT_DECORATOR_KEY = Symbol("AGENT_DECORATOR");

/**
 * Class method decorator that marks a method as an agent definition.
 * Use `agentsFrom(instance)` to extract decorated methods as Agent instances.
 */
export function AgentDec(options: Omit<AgentOptions, "instructions"> & { instructions?: string }) {
  return function (target: object, propertyKey: string, descriptor: PropertyDescriptor): void {
    if (!descriptor.value) return;

    Object.defineProperty(descriptor.value, AGENT_DECORATOR_KEY, {
      value: { ...options, _methodName: propertyKey },
      writable: false,
      enumerable: false,
      configurable: false,
    });
  };
}

/**
 * Extract all @AgentDec-decorated methods from a class instance as Agent instances.
 */
export function agentsFrom(instance: object): Agent[] {
  const agents: Agent[] = [];
  const proto = Object.getPrototypeOf(instance);
  const propertyNames = Object.getOwnPropertyNames(proto);

  for (const key of propertyNames) {
    if (key === "constructor") continue;
    const descriptor = Object.getOwnPropertyDescriptor(proto, key);
    if (!descriptor?.value || typeof descriptor.value !== "function") continue;

    const metadata = (descriptor.value as Record<symbol, unknown>)[AGENT_DECORATOR_KEY] as
      | (AgentOptions & { _methodName: string })
      | undefined;

    if (!metadata) continue;

    agents.push(
      new Agent({
        name: metadata.name ?? metadata._methodName,
        model: metadata.model,
        instructions: metadata.instructions as string | undefined,
        tools: metadata.tools,
        agents: metadata.agents,
        strategy: metadata.strategy,
        maxTurns: metadata.maxTurns,
        maxTokens: metadata.maxTokens,
        temperature: metadata.temperature,
        timeoutSeconds: metadata.timeoutSeconds,
        external: metadata.external,
        metadata: metadata.metadata,
        enablePlanning: metadata.enablePlanning,
        credentials: metadata.credentials,
      }),
    );
  }

  return agents;
}

// ── agent() functional wrapper ────────────────────────────

/**
 * Functional alternative to `new Agent()`.
 * Creates an Agent from a function (which becomes the instructions callable)
 * and additional options.
 */
export function agent(
  fn: (...args: unknown[]) => string,
  options: Omit<AgentOptions, "instructions"> & { name: string },
): Agent {
  return new Agent({
    ...options,
    instructions: fn,
  });
}
