// ── Termination conditions ──────────────────────────────

/**
 * Context passed to shouldTerminate() for evaluation.
 */
export interface TerminationContext {
  result: string;
  messages: unknown[];
  iteration: number;
  token_usage?: Record<string, number>;
}

/**
 * Result of evaluating a termination condition.
 */
export interface TerminationResult {
  shouldTerminate: boolean;
  reason: string;
}

/**
 * Abstract base class for termination conditions.
 * Supports compositional `.and()` and `.or()` operators.
 */
export abstract class TerminationCondition {
  /**
   * Combine with another condition via AND — both must be met.
   */
  and(other: TerminationCondition): AndCondition {
    return new AndCondition(this, other);
  }

  /**
   * Combine with another condition via OR — either can trigger.
   */
  or(other: TerminationCondition): OrCondition {
    return new OrCondition(this, other);
  }

  /**
   * Evaluate whether the agent should stop.
   */
  abstract shouldTerminate(context: TerminationContext): TerminationResult;

  /**
   * Serialize to the wire format object.
   */
  abstract toJSON(): object;
}

// ── Concrete conditions ─────────────────────────────────

/**
 * Terminate when a specific text is mentioned in the output.
 */
export class TextMention extends TerminationCondition {
  readonly text: string;
  readonly caseSensitive: boolean;

  constructor(text: string, caseSensitive = false) {
    super();
    this.text = text;
    this.caseSensitive = caseSensitive;
  }

  shouldTerminate(context: TerminationContext): TerminationResult {
    let result = String(context.result ?? '');
    let text = this.text;
    if (!this.caseSensitive) {
      result = result.toLowerCase();
      text = text.toLowerCase();
    }
    if (result.includes(text)) {
      return { shouldTerminate: true, reason: `Text '${this.text}' found in output` };
    }
    return { shouldTerminate: false, reason: '' };
  }

  toJSON(): object {
    return {
      type: 'text_mention',
      text: this.text,
      caseSensitive: this.caseSensitive,
    };
  }
}

/**
 * Terminate when a specific stop message is received.
 */
export class StopMessage extends TerminationCondition {
  readonly stopMessage: string;

  constructor(stopMessage: string) {
    super();
    this.stopMessage = stopMessage;
  }

  shouldTerminate(context: TerminationContext): TerminationResult {
    const result = String(context.result ?? '').trim();
    if (result === this.stopMessage) {
      return { shouldTerminate: true, reason: `Stop message '${this.stopMessage}' received` };
    }
    return { shouldTerminate: false, reason: '' };
  }

  toJSON(): object {
    return {
      type: 'stop_message',
      stopMessage: this.stopMessage,
    };
  }
}

/**
 * Terminate after a maximum number of messages.
 */
export class MaxMessage extends TerminationCondition {
  readonly maxMessages: number;

  constructor(maxMessages: number) {
    super();
    this.maxMessages = maxMessages;
  }

  shouldTerminate(context: TerminationContext): TerminationResult {
    const messages = Array.isArray(context.messages) ? context.messages : [];
    if (messages.length >= this.maxMessages) {
      return {
        shouldTerminate: true,
        reason: `Message count (${messages.length}) >= limit (${this.maxMessages})`,
      };
    }
    return { shouldTerminate: false, reason: '' };
  }

  toJSON(): object {
    return {
      type: 'max_message',
      maxMessages: this.maxMessages,
    };
  }
}

/**
 * Terminate when token usage exceeds specified limits.
 */
export class TokenUsageCondition extends TerminationCondition {
  readonly maxTotalTokens?: number;
  readonly maxPromptTokens?: number;
  readonly maxCompletionTokens?: number;

  constructor(options: {
    maxTotalTokens?: number;
    maxPromptTokens?: number;
    maxCompletionTokens?: number;
  }) {
    super();
    this.maxTotalTokens = options.maxTotalTokens;
    this.maxPromptTokens = options.maxPromptTokens;
    this.maxCompletionTokens = options.maxCompletionTokens;
  }

  shouldTerminate(context: TerminationContext): TerminationResult {
    const usage = context.token_usage ?? {};
    const total = usage.total_tokens ?? 0;
    const prompt = usage.prompt_tokens ?? 0;
    const completion = usage.completion_tokens ?? 0;

    if (this.maxTotalTokens !== undefined && total >= this.maxTotalTokens) {
      return {
        shouldTerminate: true,
        reason: `Total tokens (${total}) >= limit (${this.maxTotalTokens})`,
      };
    }
    if (this.maxPromptTokens !== undefined && prompt >= this.maxPromptTokens) {
      return {
        shouldTerminate: true,
        reason: `Prompt tokens (${prompt}) >= limit (${this.maxPromptTokens})`,
      };
    }
    if (this.maxCompletionTokens !== undefined && completion >= this.maxCompletionTokens) {
      return {
        shouldTerminate: true,
        reason: `Completion tokens (${completion}) >= limit (${this.maxCompletionTokens})`,
      };
    }
    return { shouldTerminate: false, reason: '' };
  }

  toJSON(): object {
    const result: Record<string, unknown> = { type: 'token_usage' };
    if (this.maxTotalTokens !== undefined) result.maxTotalTokens = this.maxTotalTokens;
    if (this.maxPromptTokens !== undefined) result.maxPromptTokens = this.maxPromptTokens;
    if (this.maxCompletionTokens !== undefined) result.maxCompletionTokens = this.maxCompletionTokens;
    return result;
  }
}

// ── Composite conditions ────────────────────────────────

/**
 * AND composition — all conditions must be met.
 * Flattens nested AND children: A.and(B).and(C) → and([A, B, C])
 * This matches the Python SDK's flattening behavior for wire format parity.
 */
export class AndCondition extends TerminationCondition {
  readonly conditions: TerminationCondition[];

  constructor(...conditions: TerminationCondition[]) {
    super();
    // Flatten nested ANDs: if a child is AndCondition, merge its children
    const flattened: TerminationCondition[] = [];
    for (const c of conditions) {
      if (c instanceof AndCondition) {
        flattened.push(...c.conditions);
      } else {
        flattened.push(c);
      }
    }
    this.conditions = flattened;
  }

  shouldTerminate(context: TerminationContext): TerminationResult {
    const reasons: string[] = [];
    for (const cond of this.conditions) {
      const result = cond.shouldTerminate(context);
      if (!result.shouldTerminate) {
        return { shouldTerminate: false, reason: '' };
      }
      if (result.reason) reasons.push(result.reason);
    }
    return { shouldTerminate: true, reason: reasons.join(' AND ') };
  }

  toJSON(): object {
    return {
      type: 'and',
      conditions: this.conditions.map((c) => c.toJSON()),
    };
  }
}

/**
 * OR composition — any condition can trigger termination.
 * Flattens nested OR children: A.or(B).or(C) → or([A, B, C])
 * This matches the Python SDK's flattening behavior for wire format parity.
 */
export class OrCondition extends TerminationCondition {
  readonly conditions: TerminationCondition[];

  constructor(...conditions: TerminationCondition[]) {
    super();
    // Flatten nested ORs: if a child is OrCondition, merge its children
    const flattened: TerminationCondition[] = [];
    for (const c of conditions) {
      if (c instanceof OrCondition) {
        flattened.push(...c.conditions);
      } else {
        flattened.push(c);
      }
    }
    this.conditions = flattened;
  }

  shouldTerminate(context: TerminationContext): TerminationResult {
    for (const cond of this.conditions) {
      const result = cond.shouldTerminate(context);
      if (result.shouldTerminate) return result;
    }
    return { shouldTerminate: false, reason: '' };
  }

  toJSON(): object {
    return {
      type: 'or',
      conditions: this.conditions.map((c) => c.toJSON()),
    };
  }
}
