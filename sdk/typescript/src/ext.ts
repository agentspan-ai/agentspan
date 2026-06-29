import { Agent } from "./agent.js";
import type { AgentOptions } from "./agent.js";

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
