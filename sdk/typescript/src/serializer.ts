import { toJsonSchema } from "./tool.js";
import { Agent, PromptTemplate } from "./agent.js";
import type {
  CallbackHandler,
  TerminationCondition,
  HandoffCondition,
  GateCondition,
  ConversationMemory,
} from "./agent.js";
import { normalizeToolInput, isZodSchema } from "./tool.js";
import type { ToolDef } from "./types.js";

// ── Wire format types ─────────────────────────────────────

/**
 * Callback method → wire position mapping.
 */
const CALLBACK_POSITION_MAP: Record<string, string> = {
  onAgentStart: "before_agent",
  onAgentEnd: "after_agent",
  onModelStart: "before_model",
  onModelEnd: "after_model",
  onToolStart: "before_tool",
  onToolEnd: "after_tool",
};

// ── Helpers ───────────────────────────────────────────────

/**
 * Omit keys with null or undefined values from an object.
 */
function omitNulls(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== null && value !== undefined) {
      result[key] = value;
    }
  }
  return result;
}

/**
 * Convert a Zod or JSON Schema outputType to wire format.
 */
function serializeOutputType(
  outputType: unknown,
): { schema: object; className: string } | undefined {
  if (outputType == null) return undefined;

  if (isZodSchema(outputType)) {
    const schema = toJsonSchema(outputType) as Record<string, unknown>;
    // Use schema description or default to 'Output'
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const desc = (outputType as any).description;
    return {
      schema,
      className: typeof desc === "string" && desc.length > 0 ? desc : "Output",
    };
  }

  // Already JSON Schema
  return {
    schema: outputType as object,
    className: "Output",
  };
}

// ── AgentConfigSerializer ─────────────────────────────────

export interface SerializeOptions {
  sessionId?: string;
  media?: string[];
  idempotencyKey?: string;
}

/**
 * Serializes Agent trees to the wire format the server expects.
 * Produces the JSON payload for POST /agent/start.
 */
export class AgentConfigSerializer {
  /**
   * Produce full POST /agent/start payload.
   */
  serialize(agent: Agent, prompt?: string, options?: SerializeOptions): Record<string, unknown> {
    const payload: Record<string, unknown> = {
      agentConfig: this.serializeAgent(agent),
      prompt: prompt ?? "",
      sessionId: options?.sessionId ?? "",
      media: options?.media ?? [],
    };

    if (options?.idempotencyKey !== undefined) {
      payload.idempotencyKey = options.idempotencyKey;
    }

    return payload;
  }

  /**
   * Recursively serialize an Agent to AgentConfig JSON.
   * All keys are camelCase. Null/undefined values are omitted.
   */
  serializeAgent(agent: Agent): Record<string, unknown> {
    // Claude-code agents emit a passthrough stub — all config is consumed
    // by the worker closure, not sent to the server.
    if (agent.isClaudeCode) {
      return {
        name: agent.name,
        model: agent.model,
        metadata: { _framework_passthrough: true },
        tools: [
          {
            name: agent.name,
            toolType: "worker",
            description: "Claude Agent SDK passthrough worker",
          },
        ],
      };
    }

    const config: Record<string, unknown> = {
      name: agent.name,
    };

    // Model
    if (agent.model) config.model = agent.model;

    // Base URL (per-agent LLM provider endpoint override)
    if (agent.baseUrl) config.baseUrl = agent.baseUrl;

    // Instructions: string as-is, PromptTemplate → wire format, function → call it
    if (agent.instructions !== undefined && agent.instructions !== null) {
      config.instructions = this.serializeInstructions(agent.instructions);
    }

    // Tools
    if (agent.tools.length > 0) {
      config.tools = agent.tools.map((t) => this.serializeTool(normalizeToolInput(t)));
    }

    // Sub-agents (recursive)
    if (agent.agents.length > 0) {
      config.agents = agent.agents.map((a) => this.serializeAgent(a));
      // Strategy ONLY when agents is non-empty
      if (agent.strategy) {
        config.strategy = agent.strategy;
      }
    }

    // Router
    if (agent.router !== undefined && agent.router !== null) {
      config.router = this.serializeRouter(agent.router, agent.name);
    }

    // Output type
    const ot = serializeOutputType(agent.outputType);
    if (ot) config.outputType = ot;

    // Guardrails
    if (agent.guardrails.length > 0) {
      config.guardrails = agent.guardrails.map((g) => this.serializeGuardrail(g));
    }

    // Memory
    if (agent.memory) {
      config.memory = this.serializeMemory(agent.memory);
    }

    // Scalar fields — always emit maxTurns, timeoutSeconds, external (match Python)
    config.maxTurns = agent.maxTurns;
    if (agent.maxTokens !== undefined) config.maxTokens = agent.maxTokens;
    if (agent.temperature !== undefined) config.temperature = agent.temperature;
    config.timeoutSeconds = agent.timeoutSeconds;
    config.external = agent.external;

    // stopWhen
    if (agent.stopWhen) {
      config.stopWhen = { taskName: `${agent.name}_stop_when` };
    }

    // Termination
    if (agent.termination) {
      config.termination = this.serializeTermination(agent.termination);
    }

    // Handoffs
    if (agent.handoffs.length > 0) {
      config.handoffs = agent.handoffs.map((h) => this.serializeHandoff(h));
    }

    // Allowed transitions
    if (agent.allowedTransitions) {
      config.allowedTransitions = agent.allowedTransitions;
    }

    // Introduction
    if (agent.introduction) config.introduction = agent.introduction;

    // Metadata
    if (agent.metadata) config.metadata = agent.metadata;

    // Planner
    if (agent.planner) config.planner = agent.planner;

    // Callbacks
    if (agent.callbacks.length > 0) {
      config.callbacks = this.serializeCallbacks(agent.callbacks, agent.name);
    }

    // includeContents
    if (agent.includeContents) config.includeContents = agent.includeContents;

    // thinkingBudgetTokens → thinkingConfig
    if (agent.thinkingBudgetTokens !== undefined) {
      config.thinkingConfig = {
        enabled: true,
        budgetTokens: agent.thinkingBudgetTokens,
      };
    }

    // requiredTools
    if (agent.requiredTools && agent.requiredTools.length > 0) {
      config.requiredTools = agent.requiredTools;
    }

    // Gate
    if (agent.gate) {
      config.gate = this.serializeGate(agent.gate, agent.name);
    }

    // Code execution config
    if (agent.codeExecutionConfig) {
      config.codeExecution = agent.codeExecutionConfig;
    }

    // CLI config
    if (agent.cliConfig) {
      config.cliConfig = agent.cliConfig;
    }

    // Credentials
    if (agent.credentials && agent.credentials.length > 0) {
      config.credentials = agent.credentials;
    }

    return config;
  }

  /**
   * Serialize a ToolDef to ToolConfig JSON.
   */
  serializeTool(toolDef: ToolDef): Record<string, unknown> {
    const config: Record<string, unknown> = {
      name: toolDef.name,
      description: toolDef.description,
      inputSchema: toolDef.inputSchema,
      toolType: toolDef.toolType,
    };

    if (toolDef.outputSchema) config.outputSchema = toolDef.outputSchema;
    if (toolDef.approvalRequired !== undefined) {
      config.approvalRequired = toolDef.approvalRequired;
    }
    if (toolDef.timeoutSeconds !== undefined) {
      config.timeoutSeconds = toolDef.timeoutSeconds;
    }

    // Handle guardrails
    if (toolDef.guardrails && toolDef.guardrails.length > 0) {
      config.guardrails = toolDef.guardrails.map((g) => this.serializeGuardrail(g));
    }

    // Handle agent_tool special case
    if (toolDef.toolType === "agent_tool" && toolDef.config) {
      const toolConfig = { ...toolDef.config };
      const agentRef = toolConfig.agent;
      delete toolConfig.agent;

      // Serialize the nested agent
      if (agentRef instanceof Agent) {
        config.config = {
          ...toolConfig,
          agentConfig: this.serializeAgent(agentRef),
        };
      } else {
        config.config = toolConfig;
      }
    } else if (toolDef.config && Object.keys(toolDef.config).length > 0) {
      config.config = toolDef.config;
    }

    return omitNulls(config);
  }

  /**
   * Serialize a guardrail to wire format (per spec §5.4).
   * Normalizes RegexGuardrail/LLMGuardrail instances via toGuardrailDef().
   */
  serializeGuardrail(guard: unknown): Record<string, unknown> {
    if (guard == null || typeof guard !== "object") {
      return {};
    }

    // Normalize class instances (RegexGuardrail, LLMGuardrail) via toGuardrailDef()
    let g = guard as Record<string, unknown>;
    if (typeof g.toGuardrailDef === "function") {
      g = (g.toGuardrailDef as () => Record<string, unknown>)();
    }

    const result: Record<string, unknown> = {};

    // Copy known fields
    if (g.name !== undefined) result.name = g.name;
    if (g.position !== undefined) result.position = g.position;
    if (g.onFail !== undefined) result.onFail = g.onFail;
    if (g.maxRetries !== undefined) result.maxRetries = g.maxRetries;
    if (g.guardrailType !== undefined) result.guardrailType = g.guardrailType;
    if (g.patterns !== undefined) result.patterns = g.patterns;
    if (g.mode !== undefined) result.mode = g.mode;
    if (g.message !== undefined) result.message = g.message;
    if (g.model !== undefined) result.model = g.model;
    if (g.policy !== undefined) result.policy = g.policy;
    if (g.maxTokens !== undefined) result.maxTokens = g.maxTokens;
    if (g.taskName !== undefined) result.taskName = g.taskName;

    return result;
  }

  /**
   * Serialize a termination condition recursively (AND/OR composition).
   */
  serializeTermination(cond: TerminationCondition): Record<string, unknown> {
    // Use toJSON if available
    if (typeof cond.toJSON === "function") {
      return cond.toJSON() as Record<string, unknown>;
    }

    // Raw object passthrough
    return cond as unknown as Record<string, unknown>;
  }

  /**
   * Serialize a handoff condition.
   */
  serializeHandoff(handoff: HandoffCondition): Record<string, unknown> {
    if (typeof handoff.toJSON === "function") {
      return handoff.toJSON() as Record<string, unknown>;
    }
    return handoff as unknown as Record<string, unknown>;
  }

  // ── Private helpers ───────────────────────────────────

  private serializeInstructions(
    instructions: string | PromptTemplate | ((...args: unknown[]) => string),
  ): unknown {
    if (typeof instructions === "string") {
      return instructions;
    }

    if (instructions instanceof PromptTemplate) {
      const tmpl: Record<string, unknown> = {
        type: "prompt_template",
        name: instructions.name,
      };
      if (instructions.variables) tmpl.variables = instructions.variables;
      if (instructions.version !== undefined) tmpl.version = instructions.version;
      return tmpl;
    }

    if (typeof instructions === "function") {
      return instructions();
    }

    return instructions;
  }

  private serializeRouter(
    router: Agent | ((...args: unknown[]) => string),
    agentName: string,
  ): unknown {
    if (router instanceof Agent) {
      return this.serializeAgent(router);
    }
    if (typeof router === "function") {
      return { taskName: `${agentName}_router_fn` };
    }
    return router;
  }

  private serializeMemory(memory: ConversationMemory): Record<string, unknown> {
    const result: Record<string, unknown> = {
      messages: memory.toChatMessages(),
    };
    if (memory.maxMessages !== undefined) {
      result.maxMessages = memory.maxMessages;
    }
    return result;
  }

  private serializeCallbacks(
    callbacks: CallbackHandler[],
    agentName: string,
  ): Record<string, unknown>[] {
    const result: Record<string, unknown>[] = [];

    for (const handler of callbacks) {
      for (const [methodName, wirePosition] of Object.entries(CALLBACK_POSITION_MAP)) {
        if (typeof (handler as Record<string, unknown>)[methodName] === "function") {
          result.push({
            position: wirePosition,
            taskName: `${agentName}_${wirePosition}`,
          });
        }
      }
    }

    return result;
  }

  private serializeGate(gate: GateCondition, agentName: string): Record<string, unknown> {
    // TextGate: has type 'text_contains' or text + caseSensitive
    if (gate.type === "text_contains" || (gate.text !== undefined && gate.fn === undefined)) {
      return {
        type: "text_contains",
        text: gate.text ?? "",
        ...(gate.caseSensitive !== undefined && {
          caseSensitive: gate.caseSensitive,
        }),
      };
    }

    // If it has toJSON, use it
    if (typeof gate.toJSON === "function") {
      return gate.toJSON() as Record<string, unknown>;
    }

    // Custom gate (function-based)
    return { taskName: `${agentName}_gate` };
  }
}
