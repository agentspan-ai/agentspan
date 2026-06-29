import { describe, it, expect, vi } from "vitest";
import { spawnSync } from "child_process";
import { makeCliTool } from "../../src/cli-config.js";
import { TerminalToolError } from "../../src/errors.js";

// Mock spawnSync
vi.mock("child_process", () => ({
  execSync: vi.fn(),
  spawnSync: vi.fn(),
}));

const mockedSpawnSync = vi.mocked(spawnSync);

describe("makeCliTool", () => {
  it("returns success with exit_code on zero exit", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "hello world\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const result = await tool.func!({ command: "echo", args: ["hello"] });

    expect(result).toEqual({
      status: "success",
      exit_code: 0,
      stdout: "hello world\n",
      stderr: "",
    });
  });

  it("returns error result with output on non-zero exit code", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 1,
      stdout: "some output",
      stderr: "fatal: not a git repo",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const result = await tool.func!({ command: "git", args: ["status"] });

    expect(result).toEqual({
      status: "error",
      exit_code: 1,
      stdout: "some output",
      stderr: "fatal: not a git repo",
    });
  });

  it("throws TerminalToolError on timeout", async () => {
    const err = new Error("SIGTERM") as any;
    err.killed = true;
    err.signal = "SIGTERM";
    mockedSpawnSync.mockReturnValue({
      status: null,
      stdout: "",
      stderr: "",
      error: err,
      signal: "SIGTERM",
      pid: 1,
      output: [],
    } as any);

    const tool = makeCliTool({ allowedCommands: [], timeout: 5 }, "test_agent");

    await expect(tool.func!({ command: "sleep", args: ["100"] })).rejects.toThrow(
      TerminalToolError,
    );
    await expect(tool.func!({ command: "sleep", args: ["100"] })).rejects.toThrow(/timed out/);
  });

  it("throws TerminalToolError on command not found", async () => {
    const err = new Error("ENOENT: no such file") as any;
    mockedSpawnSync.mockReturnValue({
      status: null,
      stdout: "",
      stderr: "",
      error: err,
      signal: null,
      pid: 1,
      output: [],
    } as any);

    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");

    await expect(tool.func!({ command: "nonexistent" })).rejects.toThrow(TerminalToolError);
    await expect(tool.func!({ command: "nonexistent" })).rejects.toThrow(/not found/);
  });

  it("preserves stdout and stderr on non-zero exit", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 128,
      stdout: "remote: Repository not found.\n",
      stderr: "fatal: repository not found",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const result = await tool.func!({ command: "git", args: ["push"] });

    expect(result).toEqual({
      status: "error",
      exit_code: 128,
      stdout: "remote: Repository not found.\n",
      stderr: "fatal: repository not found",
    });
  });

  it("rejects disallowed commands", async () => {
    const tool = makeCliTool({ allowedCommands: ["git"] }, "test_agent");

    await expect(tool.func!({ command: "rm", args: ["-rf", "/"] })).rejects.toThrow(/not allowed/);
  });

  it("blocks shell mode when disabled", async () => {
    const tool = makeCliTool({ allowedCommands: [], allowShell: false }, "test_agent");

    await expect(tool.func!({ command: "echo", shell: true })).rejects.toThrow(
      /Shell mode is disabled/,
    );
  });

  it("writes stdout to toolContext.state when context_key is set", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "/tmp/abc123\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const toolContext = { state: {} as Record<string, unknown> };
    const result = await tool.func!({
      command: "mktemp",
      args: ["-d"],
      context_key: "working_dir",
      __toolContext__: toolContext,
    });
    expect((result as any).status).toBe("success");
    expect(toolContext.state).toEqual({ working_dir: "/tmp/abc123" });
  });

  it("falls back to stderr for context_key when stdout is empty", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "",
      stderr: "Cloning into '/tmp/repo'...\n",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const toolContext = { state: {} as Record<string, unknown> };
    const result = await tool.func!({
      command: "gh",
      args: ["repo", "clone", "org/repo"],
      context_key: "repo",
      __toolContext__: toolContext,
    });
    expect((result as any).status).toBe("success");
    expect(toolContext.state).toEqual({ repo: "Cloning into '/tmp/repo'..." });
  });

  it("does not write to toolContext.state on non-zero exit", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 1,
      stdout: "out",
      stderr: "err",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const toolContext = { state: {} as Record<string, unknown> };
    const result = await tool.func!({
      command: "false",
      context_key: "result",
      __toolContext__: toolContext,
    });
    expect((result as any).status).toBe("error");
    expect(toolContext.state).toEqual({});
  });

  it("empty context_key is a no-op", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "val\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const toolContext = { state: {} as Record<string, unknown> };
    await tool.func!({ command: "echo", context_key: "", __toolContext__: toolContext });
    expect(toolContext.state).toEqual({});
  });

  it("works without __toolContext__ (backward compat)", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "val\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const result = await tool.func!({ command: "echo", context_key: "x" });
    expect((result as any).status).toBe("success");
    // No crash, context_key silently ignored
  });

  it("preserves existing context state on tool failure", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 1,
      stdout: "",
      stderr: "fail",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const toolContext = { state: { existing: "value" } as Record<string, unknown> };
    const result = await tool.func!({
      command: "false",
      context_key: "new_key",
      __toolContext__: toolContext,
    });
    expect((result as any).status).toBe("error");
    expect(toolContext.state).toEqual({ existing: "value" });
  });

  it("accepts a full command line packed into `command` and validates on the executable", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "repo1\nrepo2\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: ["gh"] }, "test_agent");
    const result = await tool.func!({ command: "gh repo list --limit 5" });

    expect((result as any).status).toBe("success");
    // Executable tokenized out; remaining tokens become argv.
    expect(mockedSpawnSync).toHaveBeenCalledWith(
      "gh",
      ["repo", "list", "--limit", "5"],
      expect.any(Object),
    );
  });

  it("rejects a disallowed full command line keyed on the executable", async () => {
    const tool = makeCliTool({ allowedCommands: ["git"] }, "test_agent");

    await expect(tool.func!({ command: "rm -rf /" })).rejects.toThrow(/Command 'rm' is not allowed/);
  });

  it("strips a path prefix from the executable before whitelist check", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "ok\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: ["git"] }, "test_agent");
    const result = await tool.func!({ command: "/usr/bin/git status -s" });

    expect((result as any).status).toBe("success");
    expect(mockedSpawnSync).toHaveBeenCalledWith(
      "/usr/bin/git",
      ["status", "-s"],
      expect.any(Object),
    );
  });

  it("merges args embedded in the command line with the explicit args list", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "ok\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: ["git"] }, "test_agent");
    const result = await tool.func!({ command: "git commit", args: ["-m", "msg"] });

    expect((result as any).status).toBe("success");
    expect(mockedSpawnSync).toHaveBeenCalledWith(
      "git",
      ["commit", "-m", "msg"],
      expect.any(Object),
    );
  });

  it("honors quoted arguments in the command line", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "ok\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);

    const tool = makeCliTool({ allowedCommands: ["git"] }, "test_agent");
    const result = await tool.func!({ command: 'git commit -m "hello world"' });

    expect((result as any).status).toBe("success");
    expect(mockedSpawnSync).toHaveBeenCalledWith(
      "git",
      ["commit", "-m", "hello world"],
      expect.any(Object),
    );
  });

  it("context_key _state_updates does not corrupt internals", async () => {
    mockedSpawnSync.mockReturnValue({
      status: 0,
      stdout: "val\n",
      stderr: "",
      pid: 1,
      output: [],
      signal: null,
    } as any);
    const tool = makeCliTool({ allowedCommands: [] }, "test_agent");
    const toolContext = { state: {} as Record<string, unknown> };
    const result = await tool.func!({
      command: "echo",
      context_key: "_state_updates",
      __toolContext__: toolContext,
    });
    expect((result as any).status).toBe("success");
    expect(toolContext.state["_state_updates"]).toBe("val");
  });
});
