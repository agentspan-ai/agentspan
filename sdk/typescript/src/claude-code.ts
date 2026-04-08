/**
 * ClaudeCode configuration for Agent(model: new ClaudeCode(...)) or Agent(model: 'claude-code/opus').
 *
 * Example:
 *
 *   import { Agent, ClaudeCode, PermissionMode } from 'agentspan';
 *
 *   const reviewer = new Agent({
 *     name: 'reviewer',
 *     model: new ClaudeCode('opus', PermissionMode.ACCEPT_EDITS),
 *     instructions: 'Review code quality',
 *     tools: ['Read', 'Edit', 'Bash'],
 *   });
 *
 * Or use the slash syntax shorthand:
 *
 *   const reviewer = new Agent({ name: 'reviewer', model: 'claude-code/opus', ... });
 */

// ── Permission modes ──────────────────────────────────────

export enum PermissionMode {
  DEFAULT = "default",
  ACCEPT_EDITS = "acceptEdits",
  PLAN = "plan",
  BYPASS = "bypassPermissions",
}

// ── Model aliases ─────────────────────────────────────────

const MODEL_ALIASES: Record<string, string> = {
  opus: "claude-opus-4-6",
  sonnet: "claude-sonnet-4-6",
  haiku: "claude-haiku-4-5",
};

/**
 * Resolve a short model alias to a full model ID.
 * Returns undefined for empty alias (CLI default).
 */
export function resolveClaudeCodeModel(alias: string): string | undefined {
  if (!alias) return undefined;
  return MODEL_ALIASES[alias] ?? alias;
}

// ── ClaudeCode class ──────────────────────────────────────

/**
 * Configuration for Agent({ model: new ClaudeCode(...) }).
 *
 * Wraps Claude Code Agent SDK settings into a model object that Agent
 * can consume, converting to the `claude-code/<model>` string format.
 */
export class ClaudeCode {
  readonly modelName: string;
  readonly permissionMode: PermissionMode;

  constructor(
    modelName: string = "",
    permissionMode: PermissionMode = PermissionMode.ACCEPT_EDITS,
  ) {
    this.modelName = modelName;
    this.permissionMode = permissionMode;
  }

  /**
   * Convert to the model string format used by Agent.model.
   */
  toModelString(): string {
    if (this.modelName) {
      return `claude-code/${this.modelName}`;
    }
    return "claude-code";
  }
}
