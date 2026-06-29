// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import { describe, it, expect, vi } from "vitest";
import * as schedules from "../../src/schedules-api.js";
import type { AgentRuntime } from "../../src/runtime.js";
import type { ScheduleInfo } from "../../src/schedule.js";
import type { AgentResult } from "../../src/types.js";

const INFO: ScheduleInfo = {
  name: "digest-daily",
  shortName: "daily",
  agent: "digest",
  cron: "0 0 9 * * ?",
  timezone: "UTC",
  input: { channel: "#eng" },
  paused: false,
  pausedReason: null,
  catchup: false,
  startAt: null,
  endAt: null,
  description: null,
  nextRun: null,
  createTime: null,
  updateTime: null,
  createdBy: null,
  updatedBy: null,
};

/**
 * Build a runtime double exposing the two surfaces `runNow` needs:
 * the schedules client (get + runNow) and the workflow client (getWorkflow polling).
 */
function makeRuntime(opts: {
  executionId: string;
  statuses: string[]; // one entry consumed per poll, last repeats
  output?: Record<string, unknown>;
}): { runtime: AgentRuntime; getWorkflow: ReturnType<typeof vi.fn> } {
  const schedulesClient = {
    get: vi.fn(async (_name: string) => INFO),
    runNow: vi.fn(async (_info: ScheduleInfo) => opts.executionId),
  };

  let i = 0;
  const getWorkflow = vi.fn(async (_id: string, _includeTasks?: boolean) => {
    const status = opts.statuses[Math.min(i, opts.statuses.length - 1)];
    i += 1;
    return { workflowId: opts.executionId, status, output: opts.output ?? {} };
  });

  const runtime = {
    schedulesClient: () => schedulesClient,
    workflows: { getWorkflow },
  } as unknown as AgentRuntime;

  return { runtime, getWorkflow };
}

describe("schedules.runNow (non-blocking)", () => {
  it("returns the execution id immediately without polling", async () => {
    const { runtime, getWorkflow } = makeRuntime({ executionId: "exec-1", statuses: ["RUNNING"] });
    const id = await schedules.runNow("digest-daily", { runtime });
    expect(id).toBe("exec-1");
    expect(getWorkflow).not.toHaveBeenCalled();
  });
});

describe("schedules.runNow (wait: true)", () => {
  it("polls until terminal and resolves an AgentResult", async () => {
    const { runtime, getWorkflow } = makeRuntime({
      executionId: "exec-2",
      statuses: ["RUNNING", "RUNNING", "COMPLETED"],
      output: { result: "done" },
    });

    const res = (await schedules.runNow("digest-daily", {
      runtime,
      wait: true,
      pollIntervalMs: 1,
    })) as AgentResult;

    // Polled at least until the terminal status appeared.
    expect(getWorkflow.mock.calls.length).toBe(3);
    expect(res.executionId).toBe("exec-2");
    expect(res.status).toBe("COMPLETED");
    expect(res.isSuccess).toBe(true);
    expect(res.output).toEqual({ result: "done" });
  });

  it("times out when the workflow never reaches a terminal state", async () => {
    const { runtime } = makeRuntime({ executionId: "exec-3", statuses: ["RUNNING"] });
    await expect(
      schedules.runNow("digest-daily", { runtime, wait: true, pollIntervalMs: 1, timeoutMs: 5 }),
    ).rejects.toThrow(/did not finish/i);
  });
});
