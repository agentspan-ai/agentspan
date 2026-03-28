// ── Handoff context ─────────────────────────────────────

/**
 * Context passed to handoff condition evaluation.
 */
export interface HandoffContext {
  result: string;
  toolName?: string;
  toolResult?: string;
  messages?: unknown;
}

// ── Handoff conditions ──────────────────────────────────

/**
 * Handoff when a specific tool returns a result.
 * Optionally, only handoff when the result contains specific text.
 */
export class OnToolResult {
  readonly target: string;
  readonly toolName: string;
  readonly resultContains?: string;

  constructor(options: { target: string; toolName: string; resultContains?: string }) {
    this.target = options.target;
    this.toolName = options.toolName;
    this.resultContains = options.resultContains;
  }

  shouldHandoff(context: HandoffContext): boolean {
    const calledTool = context.toolName ?? '';
    if (calledTool !== this.toolName) return false;
    if (this.resultContains !== undefined) {
      const toolResult = String(context.toolResult ?? '');
      return toolResult.includes(this.resultContains);
    }
    return true;
  }

  toJSON(): object {
    const result: Record<string, unknown> = {
      target: this.target,
      type: 'on_tool_result',
      toolName: this.toolName,
    };
    if (this.resultContains !== undefined) {
      result.resultContains = this.resultContains;
    }
    return result;
  }
}

/**
 * Handoff when specific text is mentioned in the output.
 */
export class OnTextMention {
  readonly target: string;
  readonly text: string;

  constructor(options: { target: string; text: string }) {
    this.target = options.target;
    this.text = options.text;
  }

  shouldHandoff(context: HandoffContext): boolean {
    const result = String(context.result ?? '').toLowerCase();
    return result.includes(this.text.toLowerCase());
  }

  toJSON(): object {
    return {
      target: this.target,
      type: 'on_text_mention',
      text: this.text,
    };
  }
}

/**
 * Handoff when a custom condition function returns true.
 * The condition is registered as a worker task.
 */
export class OnCondition {
  readonly target: string;
  readonly condition: Function;
  readonly taskName: string;

  constructor(options: { target: string; condition: Function; agentName?: string }) {
    this.target = options.target;
    this.condition = options.condition;
    const agentName = options.agentName ?? 'agent';
    this.taskName = `${agentName}_handoff_check`;
  }

  shouldHandoff(context: HandoffContext): boolean {
    try {
      return !!this.condition(context);
    } catch {
      return false;
    }
  }

  toJSON(): object {
    return {
      target: this.target,
      type: 'on_condition',
      taskName: this.taskName,
    };
  }
}

// ── Gate conditions ─────────────────────────────────────

/**
 * Gate that checks if text contains a specified string.
 */
export class TextGate {
  readonly text: string;
  readonly caseSensitive: boolean;

  constructor(options: { text: string; caseSensitive?: boolean }) {
    this.text = options.text;
    this.caseSensitive = options.caseSensitive ?? false;
  }

  toJSON(): object {
    return {
      type: 'text_contains',
      text: this.text,
      caseSensitive: this.caseSensitive,
    };
  }
}

/**
 * Create a custom gate from a function.
 * The function is registered as a worker task.
 */
export function gate(
  fn: Function,
  options?: { agentName?: string },
): { taskName: string; fn: Function } {
  const agentName = options?.agentName ?? 'agent';
  return {
    taskName: `${agentName}_gate`,
    fn,
  };
}
