import { Agent } from "./agent.js";
import type { AgentOptions } from "./agent.js";

// ── UserProxyAgent ──────────────────────────────────────

export type UserProxyMode = "ALWAYS" | "TERMINATE" | "NEVER";

export interface UserProxyAgentOptions {
  name: string;
  mode: UserProxyMode;
  instructions?: string;
}

/**
 * An agent that proxies user input based on mode.
 *
 * - ALWAYS: Always prompt the user for input
 * - TERMINATE: Prompt user only on termination
 * - NEVER: Never prompt the user
 */
export class UserProxyAgent extends Agent {
  readonly mode: UserProxyMode;

  constructor(options: UserProxyAgentOptions) {
    const agentOptions: AgentOptions = {
      name: options.name,
      instructions: options.instructions ?? `User proxy agent (mode: ${options.mode})`,
      metadata: { userProxy: true, mode: options.mode },
    };
    super(agentOptions);
    this.mode = options.mode;
  }
}

// ── GPTAssistantAgent ───────────────────────────────────

export interface GPTAssistantAgentOptions {
  name: string;
  assistantId: string;
  model?: string;
  instructions?: string;
}

/**
 * An agent backed by an OpenAI GPT Assistant.
 */
export class GPTAssistantAgent extends Agent {
  readonly assistantId: string;

  constructor(options: GPTAssistantAgentOptions) {
    const agentOptions: AgentOptions = {
      name: options.name,
      model: options.model,
      instructions: options.instructions,
      metadata: { assistantId: options.assistantId },
      external: true,
    };
    super(agentOptions);
    this.assistantId = options.assistantId;
  }
}
