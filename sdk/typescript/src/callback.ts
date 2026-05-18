// ── Callback system ─────────────────────────────────────

/**
 * Abstract base class for callback handlers.
 * Subclass and override the methods you need.
 */
export abstract class CallbackHandler {
  onAgentStart?(agentName: string, prompt: string): Promise<void>;
  onAgentEnd?(agentName: string, result: unknown): Promise<void>;
  onModelStart?(agentName: string, messages: unknown[]): Promise<void>;
  onModelEnd?(agentName: string, response: unknown): Promise<void>;
  onToolStart?(agentName: string, toolName: string, args: unknown): Promise<void>;
  onToolEnd?(agentName: string, toolName: string, result: unknown): Promise<void>;
}

/**
 * Mapping from callback method names to their wire format position identifiers.
 */
export const CALLBACK_POSITIONS: Record<string, string> = {
  onAgentStart: "before_agent",
  onAgentEnd: "after_agent",
  onModelStart: "before_model",
  onModelEnd: "after_model",
  onToolStart: "before_tool",
  onToolEnd: "after_tool",
};

/**
 * Given an agent name and a callback handler, return the list of
 * `{ position, taskName }` for each non-null callback method.
 */
export function getCallbackWorkerNames(
  agentName: string,
  handler: CallbackHandler,
): Array<{ position: string; taskName: string }> {
  const result: Array<{ position: string; taskName: string }> = [];

  for (const [methodName, position] of Object.entries(CALLBACK_POSITIONS)) {
    if (typeof (handler as Record<string, unknown>)[methodName] === "function") {
      result.push({
        position,
        taskName: `${agentName}_${position}`,
      });
    }
  }

  return result;
}
