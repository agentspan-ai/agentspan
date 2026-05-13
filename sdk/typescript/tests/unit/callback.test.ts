import { describe, it, expect } from "vitest";
import { CallbackHandler, CALLBACK_POSITIONS, getCallbackWorkerNames } from "../../src/callback.js";

// ── CALLBACK_POSITIONS ──────────────────────────────────

describe("CALLBACK_POSITIONS", () => {
  it("maps all 6 callback methods to wire positions", () => {
    expect(CALLBACK_POSITIONS).toEqual({
      onAgentStart: "before_agent",
      onAgentEnd: "after_agent",
      onModelStart: "before_model",
      onModelEnd: "after_model",
      onToolStart: "before_tool",
      onToolEnd: "after_tool",
    });
  });
});

// ── getCallbackWorkerNames ──────────────────────────────

describe("getCallbackWorkerNames()", () => {
  it("returns worker names for implemented methods only", () => {
    class MyHandler extends CallbackHandler {
      async onAgentStart(_agentName: string, _prompt: string): Promise<void> {}
      async onToolEnd(_agentName: string, _toolName: string, _result: unknown): Promise<void> {}
    }

    const handler = new MyHandler();
    const workers = getCallbackWorkerNames("researcher", handler);

    expect(workers).toHaveLength(2);
    expect(workers).toContainEqual({
      position: "before_agent",
      taskName: "researcher_before_agent",
    });
    expect(workers).toContainEqual({
      position: "after_tool",
      taskName: "researcher_after_tool",
    });
  });

  it("returns all 6 workers when all methods implemented", () => {
    class FullHandler extends CallbackHandler {
      async onAgentStart(): Promise<void> {}
      async onAgentEnd(): Promise<void> {}
      async onModelStart(): Promise<void> {}
      async onModelEnd(): Promise<void> {}
      async onToolStart(): Promise<void> {}
      async onToolEnd(): Promise<void> {}
    }

    const workers = getCallbackWorkerNames("agent", new FullHandler());
    expect(workers).toHaveLength(6);

    const positions = workers.map((w) => w.position);
    expect(positions).toContain("before_agent");
    expect(positions).toContain("after_agent");
    expect(positions).toContain("before_model");
    expect(positions).toContain("after_model");
    expect(positions).toContain("before_tool");
    expect(positions).toContain("after_tool");
  });

  it("returns empty array when no methods are implemented", () => {
    class EmptyHandler extends CallbackHandler {}

    const workers = getCallbackWorkerNames("agent", new EmptyHandler());
    expect(workers).toHaveLength(0);
  });

  it("generates task names using agent name prefix", () => {
    class PartialHandler extends CallbackHandler {
      async onModelStart(): Promise<void> {}
    }

    const workers = getCallbackWorkerNames("my_agent", new PartialHandler());
    expect(workers).toHaveLength(1);
    expect(workers[0]).toEqual({
      position: "before_model",
      taskName: "my_agent_before_model",
    });
  });
});
