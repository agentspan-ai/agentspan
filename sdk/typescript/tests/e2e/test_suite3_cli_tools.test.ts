/**
 * Suite 3: CLI Tools — command execution and credential isolation.
 *
 * With secrets delegated to the Orkes host, standalone/CI has no secret
 * backend. This suite covers what remains testable without one:
 *   1. ls and mktemp succeed without credentials.
 *   2. gh (requiring a credential) does NOT succeed without a backend.
 *
 * Requires: gh CLI installed, GITHUB_TOKEN env var set.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { execSync } from "node:child_process";
import { Agent, AgentRuntime, tool } from "@agentspan-ai/sdk";
import { checkServerHealth, MODEL, TIMEOUT, getOutputText } from "./helpers";

const CRED_NAME = "GITHUB_TOKEN";
let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error("Server not available");
  runtime = new AgentRuntime();
});

afterAll(async () => {
  await runtime.shutdown();
});

// ── Tools ───────────────────────────────────────────────────────────────

const cliLs = tool(
  async (args: { path: string }) => {
    try {
      const out = execSync(`ls ${args.path}`, { timeout: 15_000 }).toString().trim();
      return `ls_ok:${out.slice(0, 200)}`;
    } catch (e: unknown) {
      return `ls_error:${(e as Error).message.slice(0, 200)}`;
    }
  },
  {
    name: "cli_ls",
    description: "List directory contents.",
    inputSchema: {
      type: "object",
      properties: { path: { type: "string", description: "Directory path" } },
      required: ["path"],
    },
  },
);

const cliMktemp = tool(
  async () => {
    try {
      const out = execSync("mktemp", { timeout: 15_000 }).toString().trim();
      return `mktemp_ok:${out}`;
    } catch (e: unknown) {
      return `mktemp_error:${(e as Error).message.slice(0, 200)}`;
    }
  },
  {
    name: "cli_mktemp",
    description: "Create a temporary file.",
    inputSchema: { type: "object", properties: {} },
  },
);

const cliGh = tool(
  async (args: { subcommand: string }) => {
    const token = process.env.GITHUB_TOKEN ?? "";
    if (!token) throw new Error("GITHUB_TOKEN not found in environment.");
    try {
      const out = execSync(`gh ${args.subcommand}`, { timeout: 30_000 }).toString().trim();
      return `gh_ok:${out.slice(0, 200)}`;
    } catch (e: unknown) {
      return `gh_error:${(e as Error).message.slice(0, 200)}`;
    }
  },
  {
    name: "cli_gh",
    description: "Run a gh CLI command. Requires GITHUB_TOKEN.",
    credentials: [CRED_NAME],
    inputSchema: {
      type: "object",
      properties: {
        subcommand: { type: "string", description: 'gh subcommand e.g. "repo list --limit 3"' },
      },
      required: ["subcommand"],
    },
  },
);

const PROMPT = `Call all three tools:
1. cli_ls with path="/tmp"
2. cli_mktemp (no arguments)
3. cli_gh with subcommand="repo list --limit 3"
Report each result.`;

function makeAgent() {
  return new Agent({
    name: "e2e_ts_cli_tools",
    model: MODEL,
    instructions:
      "You have three tools: cli_ls, cli_mktemp, cli_gh. " +
      "Call each tool exactly once as directed. Report output verbatim.",
    tools: [cliLs, cliMktemp, cliGh],
  });
}

// ── Tests ───────────────────────────────────────────────────────────────

describe("Suite 3: CLI Tools", { timeout: 600_000 }, () => {
  it.skipIf(!process.env.GITHUB_TOKEN)(
    "credential-free CLI tools succeed; credential-requiring tool fails without backend",
    async () => {
      const realToken = process.env.GITHUB_TOKEN!;

      // Runtime check: gh CLI must be installed. Cannot use skipIf since
      // it requires executing a subprocess — not a simple env var check.
      try {
        execSync("gh --version", { timeout: 5_000 });
      } catch {
        console.log("gh CLI not installed — skipping Suite 3");
        return;
      }

      const agent = makeAgent();

      // Export to env (should NOT be used by the server — no secret backend).
      process.env.GITHUB_TOKEN = realToken;

      // No credential backend — ls/mktemp succeed, gh does NOT succeed.
      const result = await runtime.run(agent, PROMPT, { timeout: TIMEOUT });
      expect(result.executionId).toBeTruthy();
      expect(["COMPLETED", "FAILED", "TERMINATED"]).toContain(result.status);

      const output = getOutputText(result as unknown as { output: unknown });
      expect(output).toContain("ls_ok");
      expect(output).toContain("mktemp_ok");
      expect(output).not.toContain("gh_ok");
    },
  );
});
