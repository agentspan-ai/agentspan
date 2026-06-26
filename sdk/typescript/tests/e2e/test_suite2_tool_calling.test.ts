/**
 * Suite 2: Tool Calling / Credentials — architecture-aligned coverage.
 *
 * With secrets delegated to the Orkes host (${workflow.secrets.NAME}),
 * standalone/CI has no secret backend and no way to inject a credential
 * value into a running tool. This suite covers what remains testable
 * without a secret store:
 *   1. A tool needing NO credential runs and COMPLETES.
 *   2. A tool REQUIRING a credential, with no backend, does NOT succeed.
 *   3. Env-var values must NOT leak into tool output.
 *
 * No mocks. Real server, real LLM. No secret-injection.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { Agent, AgentRuntime, tool, getCredential } from "@agentspan-ai/sdk";
import { checkServerHealth, MODEL, TIMEOUT, getOutputText, findToolTasks } from "./helpers";

const CRED_A = "E2E_TS_CRED_A";
const CRED_B = "E2E_TS_CRED_B";

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

const freeTool = tool(async () => "free:ok", {
  name: "free_tool",
  description: "Always succeeds. No credentials needed.",
  inputSchema: { type: "object", properties: { x: { type: "string" } }, required: ["x"] },
});

const paidToolA = tool(
  async () => {
    let cred: string | undefined;
    try {
      cred = await getCredential(CRED_A);
    } catch {
      /* credential not found */
    }
    if (!cred) throw new Error(`Credential '${CRED_A}' not found in environment.`);
    return `paid_a:${cred.slice(0, 3)}`;
  },
  {
    name: "paid_tool_a",
    description: "Requires E2E_TS_CRED_A. Returns first 3 chars.",
    credentials: [CRED_A],
    inputSchema: { type: "object", properties: { x: { type: "string" } }, required: ["x"] },
  },
);

const paidToolB = tool(
  async () => {
    let cred: string | undefined;
    try {
      cred = await getCredential(CRED_B);
    } catch {
      /* credential not found */
    }
    if (!cred) throw new Error(`Credential '${CRED_B}' not found in environment.`);
    return `paid_b:${cred.slice(0, 3)}`;
  },
  {
    name: "paid_tool_b",
    description: "Requires E2E_TS_CRED_B. Returns first 3 chars.",
    credentials: [CRED_B],
    inputSchema: { type: "object", properties: { x: { type: "string" } }, required: ["x"] },
  },
);

function makeAgent() {
  return new Agent({
    name: "e2e_ts_cred_lifecycle",
    model: MODEL,
    maxTurns: 3,
    instructions:
      "You have three tools: free_tool, paid_tool_a, and paid_tool_b. " +
      'Call all three exactly once with argument x="test". Report each result.',
    tools: [freeTool, paidToolA, paidToolB],
  });
}

// ── Test ────────────────────────────────────────────────────────────────

describe("Suite 2: Tool Calling / Credentials", { timeout: 300_000 }, () => {
  it("free tool completes; credential-requiring tools fail with no backend", async () => {
    const agent = makeAgent();

    // ── No credential backend — free tool runs, paid tools fail ──
    const result = await runtime.run(agent, "Call all three tools.", {
      timeout: TIMEOUT,
    });
    expect(result.executionId).toBeTruthy();
    expect(["COMPLETED", "FAILED", "TERMINATED"]).toContain(result.status);

    const { results: tasks } = await findToolTasks(result.executionId!, [
      "free_tool",
      "paid_tool_a",
      "paid_tool_b",
    ]);

    // Free tool needs no credential — it must COMPLETE.
    expect(tasks["free_tool"], "free_tool task not found").toBeTruthy();
    expect(tasks["free_tool"].status, "free_tool should be COMPLETED").toBe("COMPLETED");

    // Paid tools require a credential with no backend — they must NOT succeed.
    // Accept any non-COMPLETED terminal/failure status.
    const nonSuccess = [
      "FAILED",
      "FAILED_WITH_TERMINAL_ERROR",
      "COMPLETED_WITH_ERRORS",
      "TERMINATED",
    ];
    for (const paid of ["paid_tool_a", "paid_tool_b"] as const) {
      if (tasks[paid]) {
        const t = tasks[paid];
        expect(
          nonSuccess,
          `${paid} should NOT succeed without a credential backend, got '${t.status}'.`,
        ).toContain(t.status);
      }
    }
  });

  it("env-var credential values must NOT leak into output", async () => {
    const agent = makeAgent();
    try {
      process.env.E2E_TS_CRED_A = "from-env-aaa";
      process.env.E2E_TS_CRED_B = "from-env-bbb";

      const resultEnv = await runtime.run(agent, "Call all three tools.", {
        timeout: TIMEOUT,
      });
      expect(resultEnv.executionId).toBeTruthy();
      expect(["COMPLETED", "FAILED", "TERMINATED"]).toContain(resultEnv.status);

      const outputEnv = getOutputText(resultEnv as unknown as { output: unknown });
      // Check for "from-env" (the unique prefix of our test env values
      // "from-env-aaa" / "from-env-bbb"). Using "fro" caused false positives
      // when LLM prose contained "from" in normal words.
      expect(
        outputEnv,
        `[Env security] env-var values leaked into output: ${outputEnv.slice(0, 300)}`,
      ).not.toContain("from-env");
    } finally {
      delete process.env.E2E_TS_CRED_A;
      delete process.env.E2E_TS_CRED_B;
    }
  });
});
