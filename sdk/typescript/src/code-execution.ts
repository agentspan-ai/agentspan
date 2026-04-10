import { execSync } from "child_process";
import type { ToolDef } from "./types.js";

// ── Command Validator ───────────────────────────────────

/**
 * Best-effort validator that checks code against an allowed-command list.
 *
 * Scans code for shell command invocations and rejects any that are not
 * in the whitelist.
 *
 * WARNING: This is a convenience safety layer, not a security boundary.
 * Determined code can bypass regex-based detection (e.g. via eval,
 * encoded strings, or dynamic imports). For untrusted code, use
 * DockerCodeExecutor with network disabled.
 */
export class CommandValidator {
  readonly allowedCommands: ReadonlySet<string>;

  // Python patterns that invoke external commands
  private static readonly PYTHON_PATTERNS: RegExp[] = [
    // subprocess.run(["cmd", ...]) / subprocess.call(["cmd", ...]) etc.
    /subprocess\.\w+\(\s*\[?\s*["'](\S+?)["']/g,
    // os.system("cmd ...") / os.popen("cmd ...")
    /os\.(?:system|popen)\(\s*["'](\S+)/g,
    // Jupyter ! syntax
    /^\s*!(\S+)/gm,
  ];

  // Bash/shell patterns
  private static readonly BASH_COMMAND_RE = /(?:^|[|;&]\s*|`|\$\(\s*)(\w[\w.+-]*)/gm;

  private static readonly BASH_BUILTINS = new Set([
    "if",
    "then",
    "else",
    "elif",
    "fi",
    "for",
    "while",
    "do",
    "done",
    "case",
    "esac",
    "in",
    "function",
    "select",
    "until",
    "echo",
    "printf",
    "read",
    "local",
    "export",
    "unset",
    "set",
    "shift",
    "return",
    "exit",
    "true",
    "false",
    "test",
    "[",
    "[[",
    "declare",
    "typeset",
    "readonly",
    "source",
    ".",
    "eval",
    "exec",
    "trap",
    "wait",
    "break",
    "continue",
    "cd",
    "pushd",
    "popd",
    "pwd",
    "dirs",
    "hash",
    "type",
    "command",
    "builtin",
    "enable",
    "let",
    "shopt",
    "complete",
    "compgen",
  ]);

  // Heredoc delimiter pattern: << 'WORD' or << WORD or <<- WORD
  private static readonly HEREDOC_RE = /<<-?\s*'?(\w+)'?/g;

  constructor(allowedCommands: string[]) {
    this.allowedCommands = new Set(allowedCommands);
  }

  /**
   * Validate code against the allowed-command list.
   *
   * Returns null if the code passes validation, or an error
   * message string describing the violation.
   */
  validate(code: string, language: string): string | null {
    if (this.allowedCommands.size === 0) {
      return null; // no restrictions
    }

    if (language === "python" || language === "python3") {
      return this.validatePython(code);
    } else if (language === "bash" || language === "sh") {
      return this.validateBash(code);
    }
    // For other languages, skip command validation
    return null;
  }

  private validatePython(code: string): string | null {
    for (const pattern of CommandValidator.PYTHON_PATTERNS) {
      // Reset regex state for global patterns
      const re = new RegExp(pattern.source, pattern.flags);
      let match: RegExpExecArray | null;
      while ((match = re.exec(code)) !== null) {
        const raw = match[1];
        // Handle /usr/bin/cmd -> cmd
        const parts = raw.split("/");
        const cmd = parts[parts.length - 1];
        if (!this.allowedCommands.has(cmd)) {
          return (
            `Command '${cmd}' is not allowed. ` +
            `Allowed commands: ${[...this.allowedCommands].sort().join(", ")}`
          );
        }
      }
    }
    return null;
  }

  private validateBash(code: string): string | null {
    // Collect heredoc delimiters so we can skip them as "commands"
    const heredocDelimiters = new Set<string>();
    const heredocRe = new RegExp(
      CommandValidator.HEREDOC_RE.source,
      CommandValidator.HEREDOC_RE.flags,
    );
    let m: RegExpExecArray | null;
    while ((m = heredocRe.exec(code)) !== null) {
      heredocDelimiters.add(m[1]);
    }

    // Strip comments
    const lines: string[] = [];
    for (let line of code.split("\n")) {
      const stripped = line.trimStart();
      if (stripped.startsWith("#")) {
        continue;
      }
      // Remove inline comments (naive — doesn't handle quoted #)
      const commentIdx = line.indexOf(" #");
      if (commentIdx >= 0) {
        line = line.substring(0, commentIdx);
      }
      lines.push(line);
    }
    const cleaned = lines.join("\n");

    const cmdRe = new RegExp(
      CommandValidator.BASH_COMMAND_RE.source,
      CommandValidator.BASH_COMMAND_RE.flags,
    );
    let match: RegExpExecArray | null;
    while ((match = cmdRe.exec(cleaned)) !== null) {
      const cmd = match[1];
      if (CommandValidator.BASH_BUILTINS.has(cmd)) {
        continue;
      }
      if (heredocDelimiters.has(cmd)) {
        continue;
      }
      if (!this.allowedCommands.has(cmd)) {
        return (
          `Command '${cmd}' is not allowed. ` +
          `Allowed commands: ${[...this.allowedCommands].sort().join(", ")}`
        );
      }
    }
    return null;
  }
}

// ── Execution result ────────────────────────────────────

/**
 * Result of executing code.
 */
export interface ExecutionResult {
  output: string;
  error: string;
  exitCode: number;
  timedOut: boolean;
  readonly success: boolean;
}

/**
 * Create an ExecutionResult with computed `success` getter.
 */
function createExecutionResult(data: {
  output: string;
  error: string;
  exitCode: number;
  timedOut: boolean;
}): ExecutionResult {
  return {
    output: data.output,
    error: data.error,
    exitCode: data.exitCode,
    timedOut: data.timedOut,
    get success(): boolean {
      return data.exitCode === 0 && !data.timedOut;
    },
  };
}

// ── CodeExecutor abstract class ─────────────────────────

/**
 * Abstract base class for code executors.
 */
export abstract class CodeExecutor {
  /**
   * Execute code and return the result.
   */
  abstract execute(code: string, language?: string): ExecutionResult;

  /**
   * Convert this executor into a ToolDef that can be used as an agent tool.
   *
   * @param name - Override tool name (default: 'execute_code').
   * @param agentName - When provided, the tool name is prefixed:
   *   `{agentName}_execute_code`. This avoids collisions when multiple
   *   agents define code execution tools with different configs.
   */
  asTool(name?: string, agentName?: string): ToolDef {
    const baseName = name ?? "execute_code";
    const toolName = agentName ? `${agentName}_${baseName}` : baseName;
    return {
      name: toolName,
      description: "Execute code and return the result",
      inputSchema: {
        type: "object",
        properties: {
          code: { type: "string", description: "The code to execute" },
          language: { type: "string", description: "Programming language" },
        },
        required: ["code"],
      },
      toolType: "worker",
      func: async (args: Record<string, unknown>) => {
        const code = args.code as string;
        const language = args.language as string | undefined;
        return this.execute(code, language);
      },
    };
  }
}

// ── LocalCodeExecutor ───────────────────────────────────

/**
 * Execute code locally using child_process.
 */
export class LocalCodeExecutor extends CodeExecutor {
  readonly timeout: number;

  constructor(options?: { timeout?: number }) {
    super();
    this.timeout = (options?.timeout ?? 30) * 1000; // convert to ms
  }

  execute(code: string, language?: string): ExecutionResult {
    const lang = language ?? "javascript";
    let command: string;

    switch (lang) {
      case "python":
      case "python3":
        command = `python3 -c ${JSON.stringify(code)}`;
        break;
      case "javascript":
      case "js":
      case "node":
        command = `node -e ${JSON.stringify(code)}`;
        break;
      case "bash":
      case "sh":
        command = `bash -c ${JSON.stringify(code)}`;
        break;
      default:
        command = `${lang} -c ${JSON.stringify(code)}`;
        break;
    }

    try {
      const output = execSync(command, {
        timeout: this.timeout,
        encoding: "utf-8",
        stdio: ["pipe", "pipe", "pipe"],
      });

      return createExecutionResult({
        output: output.trim(),
        error: "",
        exitCode: 0,
        timedOut: false,
      });
    } catch (err: unknown) {
      const execErr = err as {
        status?: number | null;
        killed?: boolean;
        stdout?: string;
        stderr?: string;
        signal?: string;
      };

      const timedOut = execErr.killed === true || execErr.signal === "SIGTERM";

      return createExecutionResult({
        output: typeof execErr.stdout === "string" ? execErr.stdout.trim() : "",
        error: typeof execErr.stderr === "string" ? execErr.stderr.trim() : String(err),
        exitCode: execErr.status ?? 1,
        timedOut,
      });
    }
  }
}

// ── DockerCodeExecutor ──────────────────────────────────

/**
 * Execute code in a Docker container.
 */
export class DockerCodeExecutor extends CodeExecutor {
  readonly image: string;
  readonly timeout: number;
  readonly memoryLimit?: string;

  constructor(options: { image: string; timeout?: number; memoryLimit?: string }) {
    super();
    this.image = options.image;
    this.timeout = (options.timeout ?? 30) * 1000;
    this.memoryLimit = options.memoryLimit;
  }

  execute(code: string, language?: string): ExecutionResult {
    const lang = language ?? "python";
    let runCmd: string;

    switch (lang) {
      case "python":
      case "python3":
        runCmd = `python3 -c ${JSON.stringify(code)}`;
        break;
      case "javascript":
      case "js":
      case "node":
        runCmd = `node -e ${JSON.stringify(code)}`;
        break;
      default:
        runCmd = `${lang} -c ${JSON.stringify(code)}`;
        break;
    }

    const memFlag = this.memoryLimit ? ` --memory=${this.memoryLimit}` : "";
    const command = `docker run --rm${memFlag} ${this.image} ${runCmd}`;

    try {
      const output = execSync(command, {
        timeout: this.timeout,
        encoding: "utf-8",
        stdio: ["pipe", "pipe", "pipe"],
      });

      return createExecutionResult({
        output: output.trim(),
        error: "",
        exitCode: 0,
        timedOut: false,
      });
    } catch (err: unknown) {
      const execErr = err as {
        status?: number | null;
        killed?: boolean;
        stdout?: string;
        stderr?: string;
        signal?: string;
      };

      const timedOut = execErr.killed === true || execErr.signal === "SIGTERM";

      return createExecutionResult({
        output: typeof execErr.stdout === "string" ? execErr.stdout.trim() : "",
        error: typeof execErr.stderr === "string" ? execErr.stderr.trim() : String(err),
        exitCode: execErr.status ?? 1,
        timedOut,
      });
    }
  }
}

// ── JupyterCodeExecutor ─────────────────────────────────

/**
 * Execute code via a Jupyter kernel.
 * Stub implementation — requires jupyter runtime.
 */
export class JupyterCodeExecutor extends CodeExecutor {
  readonly kernelName: string;
  readonly timeout: number;

  constructor(options?: { kernelName?: string; timeout?: number }) {
    super();
    this.kernelName = options?.kernelName ?? "python3";
    this.timeout = options?.timeout ?? 30;
  }

  execute(_code: string, _language?: string): ExecutionResult {
    return createExecutionResult({
      output: "",
      error: "JupyterCodeExecutor requires a running Jupyter runtime. Not yet implemented.",
      exitCode: 1,
      timedOut: false,
    });
  }
}

// ── ServerlessCodeExecutor ──────────────────────────────

/**
 * Execute code by POSTing to a serverless endpoint.
 */
export class ServerlessCodeExecutor extends CodeExecutor {
  readonly endpoint: string;
  readonly timeout: number;
  readonly headers: Record<string, string>;

  constructor(options: { endpoint: string; timeout?: number; headers?: Record<string, string> }) {
    super();
    this.endpoint = options.endpoint;
    this.timeout = options.timeout ?? 30;
    this.headers = options.headers ?? {};
  }

  execute(code: string, language?: string): ExecutionResult {
    // Build a synchronous HTTP call via child_process for the sync interface
    const payload = JSON.stringify({ code, language: language ?? "python" });
    const headerArgs = Object.entries(this.headers)
      .map(([k, v]) => `-H ${JSON.stringify(`${k}: ${v}`)}`)
      .join(" ");

    const command = `curl -s -X POST ${headerArgs} -H "Content-Type: application/json" -d ${JSON.stringify(payload)} --max-time ${this.timeout} ${JSON.stringify(this.endpoint)}`;

    try {
      const output = execSync(command, {
        timeout: this.timeout * 1000,
        encoding: "utf-8",
        stdio: ["pipe", "pipe", "pipe"],
      });

      // Attempt to parse as JSON response
      try {
        const parsed = JSON.parse(output) as Record<string, unknown>;
        return createExecutionResult({
          output: String(parsed.output ?? parsed.result ?? output),
          error: String(parsed.error ?? ""),
          exitCode: typeof parsed.exitCode === "number" ? parsed.exitCode : 0,
          timedOut: false,
        });
      } catch {
        // Plain text response
        return createExecutionResult({
          output: output.trim(),
          error: "",
          exitCode: 0,
          timedOut: false,
        });
      }
    } catch (err: unknown) {
      const execErr = err as {
        status?: number | null;
        killed?: boolean;
        stdout?: string;
        stderr?: string;
        signal?: string;
      };

      const timedOut = execErr.killed === true || execErr.signal === "SIGTERM";

      return createExecutionResult({
        output: typeof execErr.stdout === "string" ? execErr.stdout.trim() : "",
        error: typeof execErr.stderr === "string" ? execErr.stderr.trim() : String(err),
        exitCode: execErr.status ?? 1,
        timedOut,
      });
    }
  }
}
