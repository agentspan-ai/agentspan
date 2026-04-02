/**
 * First-class CLI command execution configuration for agents.
 *
 * Provides {@link CliConfigOptions} for declarative CLI tool attachment on
 * {@link Agent}, a validation helper, and a factory function that
 * auto-creates a `run_command` tool.
 *
 * Example:
 *
 *   import { Agent } from 'agentspan';
 *
 *   // Simple — just flip the flag
 *   const agent = new Agent({
 *     name: 'ops',
 *     model: 'openai/gpt-4o',
 *     cliCommands: true,
 *     cliAllowedCommands: ['git', 'gh', 'curl'],
 *   });
 *
 *   // Full control
 *   import { CliConfigOptions } from 'agentspan';
 *
 *   const agent = new Agent({
 *     name: 'ops',
 *     model: 'openai/gpt-4o',
 *     cliConfig: {
 *       enabled: true,
 *       allowedCommands: ['git', 'gh'],
 *       timeout: 60,
 *       allowShell: true,
 *     },
 *   });
 */

import { execSync, spawnSync } from 'child_process';
import { TerminalToolError } from './errors.js';
import type { ToolDef } from './types.js';

// ── CliConfigOptions ──────────────────────────────────────

/**
 * Configuration for first-class CLI command execution on an Agent.
 *
 * This is the *options* interface used for constructing agents.
 * The existing `CliConfig` type in types.ts is the wire/serialization format.
 */
export interface CliConfigOptions {
  /** Whether CLI execution is active (default true). */
  enabled?: boolean;
  /** Command whitelist (e.g. ['git', 'gh']). Empty means no restrictions. */
  allowedCommands?: string[];
  /** Maximum execution time in seconds (default 30). */
  timeout?: number;
  /** Default working directory for commands. */
  workingDir?: string;
  /** Config-level gate: can the LLM use shell mode? */
  allowShell?: boolean;
}

// ── Validation ────────────────────────────────────────────

/**
 * Validate a command against the whitelist.
 * Strips path prefix (/usr/bin/git -> git) before checking.
 * Empty whitelist permits all commands.
 */
function validateCliCommand(command: string, allowedCommands: string[]): void {
  if (!allowedCommands || allowedCommands.length === 0) {
    return; // no restrictions
  }
  // Strip path prefix
  const parts = command.split('/');
  const base = parts[parts.length - 1];
  if (!allowedCommands.includes(base)) {
    throw new Error(
      `Command '${base}' is not allowed. ` +
        `Allowed commands: ${[...allowedCommands].sort().join(', ')}`,
    );
  }
}

// ── Tool factory ──────────────────────────────────────────

/**
 * Create a ToolDef for CLI command execution.
 *
 * The returned ToolDef can be appended to Agent.tools directly.
 * The tool name is prefixed with the agent name to avoid collisions
 * when multiple agents define CLI tools with different allowed commands.
 */
export function makeCliTool(
  config: CliConfigOptions,
  agentName: string,
): ToolDef {
  const allowedCommands = config.allowedCommands ?? [];
  const timeout = config.timeout ?? 30;
  const workingDir = config.workingDir;
  const allowShell = config.allowShell ?? false;
  const taskName = agentName ? `${agentName}_run_command` : 'run_command';

  // Build dynamic description
  let desc = `Run a CLI command directly. Timeout: ${timeout}s.`;
  if (allowedCommands.length > 0) {
    desc += ` Allowed commands: ${[...allowedCommands].sort().join(', ')}.`;
  }
  if (!allowShell) {
    desc += ' Shell mode is disabled — do not set shell=true.';
  }
  desc += ' If you need to save a command\'s output for later pipeline steps, set context_key. Well-known keys: repo, branch, working_dir, issue_number, pr_url, commit_sha.';

  return {
    name: taskName,
    description: desc,
    inputSchema: {
      type: 'object',
      properties: {
        command: { type: 'string', description: 'The CLI command to execute' },
        args: {
          type: 'array',
          items: { type: 'string' },
          description: 'Command arguments',
        },
        cwd: {
          type: 'string',
          description: 'Working directory for the command',
        },
        shell: {
          type: 'boolean',
          description: 'Whether to run via shell',
        },
        context_key: {
          type: 'string',
          description: 'If set, saves stdout to context state under this key on success. Well-known keys: repo, branch, working_dir, issue_number, pr_url, commit_sha.',
        },
      },
      required: ['command'],
    },
    toolType: 'worker',
    config: { allowedCommands: [...allowedCommands] },
    func: async (args: Record<string, unknown>) => {
      // Extract context fields before command processing
      const toolContext = args.__toolContext__ as { state: Record<string, unknown> } | undefined;
      const contextKey = args.context_key as string | undefined;
      delete args.__toolContext__;
      delete args.context_key;

      const command = args.command as string;
      if (!command || typeof command !== 'string') {
        return {
          status: 'error',
          stdout: '',
          stderr: 'No command provided.',
        };
      }

      // Validate against whitelist
      validateCliCommand(command, allowedCommands);

      // Shell gate
      const useShell = args.shell === true;
      if (useShell && !allowShell) {
        throw new Error(
          'Shell mode is disabled for this agent. Do not set shell=true.',
        );
      }

      // Normalise args
      let cmdArgs = (args.args as string[]) ?? [];
      if (!Array.isArray(cmdArgs)) {
        cmdArgs = [String(cmdArgs)];
      }

      // Resolve working directory
      const effectiveCwd =
        (args.cwd as string) || workingDir || undefined;

      // Use spawnSync to capture both stdout and stderr on success
      // (execSync only returns stdout, losing stderr from commands like gh clone)
      const result = spawnSync(command, cmdArgs.map(String), {
        timeout: timeout * 1000,
        encoding: 'utf-8',
        cwd: effectiveCwd,
        shell: useShell ? '/bin/sh' : undefined,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      if (result.error) {
        const err = result.error as NodeJS.ErrnoException & { killed?: boolean; signal?: string };
        if (err.killed || result.signal === 'SIGTERM') {
          throw new TerminalToolError(`Command timed out after ${timeout}s`);
        }
        if (err.message?.includes('ENOENT')) {
          throw new TerminalToolError(`Command not found: ${command}`);
        }
        throw new TerminalToolError(err.message ?? String(err));
      }

      const stdout = result.stdout ?? '';
      const stderr = result.stderr ?? '';

      if (result.status === 0) {
        if (contextKey && toolContext) {
          // Prefer stdout; fall back to stderr (e.g. git clone outputs to stderr)
          const value = stdout.trim() || stderr.trim();
          if (value) toolContext.state[contextKey] = value;
        }
        return { status: 'success', exit_code: 0, stdout, stderr };
      }

      return {
        status: 'error',
        exit_code: result.status ?? 1,
        stdout,
        stderr,
      };
    },
  };
}
