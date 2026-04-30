import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  coerceValue,
  extractToolContext,
  captureStateMutations,
  appendStateUpdates,
  stripInternalKeys,
  recordFailure,
  recordSuccess,
  isCircuitBreakerOpen,
  resetCircuitBreaker,
  resetAllCircuitBreakers,
  WorkerManager,
} from "../../src/worker.js";
import { clearCredentialContext } from "../../src/credentials.js";

// ── coerceValue ─────────────────────────────────────────

describe("coerceValue", () => {
  describe("null/empty handling", () => {
    it("returns null unchanged", () => {
      expect(coerceValue(null)).toBeNull();
    });

    it("returns undefined unchanged", () => {
      expect(coerceValue(undefined)).toBeUndefined();
    });

    it("returns value unchanged when targetType is undefined", () => {
      expect(coerceValue("hello")).toBe("hello");
    });

    it("returns value unchanged when targetType is empty string", () => {
      expect(coerceValue("hello", "")).toBe("hello");
    });
  });

  describe("type match short-circuit", () => {
    it("returns string unchanged for string target", () => {
      expect(coerceValue("hello", "string")).toBe("hello");
    });

    it("returns number unchanged for number target", () => {
      expect(coerceValue(42, "number")).toBe(42);
    });

    it("returns boolean unchanged for boolean target", () => {
      expect(coerceValue(true, "boolean")).toBe(true);
    });

    it("returns object unchanged for object target", () => {
      const obj = { a: 1 };
      expect(coerceValue(obj, "object")).toBe(obj);
    });
  });

  describe("string to object/array via JSON", () => {
    it("parses JSON string to object", () => {
      expect(coerceValue('{"a":1}', "object")).toEqual({ a: 1 });
    });

    it("parses JSON string to array", () => {
      expect(coerceValue("[1,2,3]", "array")).toEqual([1, 2, 3]);
    });

    it("returns original string on invalid JSON", () => {
      expect(coerceValue("not json", "object")).toBe("not json");
    });

    it("returns original string on invalid JSON for array target", () => {
      expect(coerceValue("not json", "array")).toBe("not json");
    });
  });

  describe("object/array to string via JSON", () => {
    it("stringifies object to string", () => {
      expect(coerceValue({ a: 1 }, "string")).toBe('{"a":1}');
    });

    it("stringifies array to string", () => {
      expect(coerceValue([1, 2, 3], "string")).toBe("[1,2,3]");
    });
  });

  describe("string to number", () => {
    it("converts numeric string to number", () => {
      expect(coerceValue("42", "number")).toBe(42);
    });

    it("converts float string to number", () => {
      expect(coerceValue("3.14", "number")).toBe(3.14);
    });

    it("returns original string for NaN", () => {
      expect(coerceValue("not-a-number", "number")).toBe("not-a-number");
    });

    it("converts zero string", () => {
      expect(coerceValue("0", "number")).toBe(0);
    });

    it("converts negative string", () => {
      expect(coerceValue("-5", "number")).toBe(-5);
    });
  });

  describe("string to boolean", () => {
    it('converts "true" to true', () => {
      expect(coerceValue("true", "boolean")).toBe(true);
    });

    it('converts "1" to true', () => {
      expect(coerceValue("1", "boolean")).toBe(true);
    });

    it('converts "yes" to true', () => {
      expect(coerceValue("yes", "boolean")).toBe(true);
    });

    it('converts "false" to false', () => {
      expect(coerceValue("false", "boolean")).toBe(false);
    });

    it('converts "0" to false', () => {
      expect(coerceValue("0", "boolean")).toBe(false);
    });

    it('converts "no" to false', () => {
      expect(coerceValue("no", "boolean")).toBe(false);
    });

    it("is case-insensitive", () => {
      expect(coerceValue("TRUE", "boolean")).toBe(true);
      expect(coerceValue("False", "boolean")).toBe(false);
      expect(coerceValue("YES", "boolean")).toBe(true);
      expect(coerceValue("NO", "boolean")).toBe(false);
    });

    it("returns original for unrecognized boolean string", () => {
      expect(coerceValue("maybe", "boolean")).toBe("maybe");
    });
  });

  describe("fallback", () => {
    it("returns original value for unknown conversion", () => {
      expect(coerceValue(42, "boolean")).toBe(42);
    });

    it("returns original value for unrecognized target type", () => {
      expect(coerceValue("hello", "custom_type")).toBe("hello");
    });

    it("is case-insensitive on target type", () => {
      expect(coerceValue("42", "Number")).toBe(42);
      expect(coerceValue("true", "Boolean")).toBe(true);
    });
  });
});

// ── Circuit breaker ─────────────────────────────────────

describe("Circuit breaker", () => {
  beforeEach(() => {
    resetAllCircuitBreakers();
  });

  it("is closed by default", () => {
    expect(isCircuitBreakerOpen("test_tool")).toBe(false);
  });

  it("opens after 10 consecutive failures", () => {
    for (let i = 0; i < 9; i++) {
      recordFailure("test_tool");
      expect(isCircuitBreakerOpen("test_tool")).toBe(false);
    }
    recordFailure("test_tool");
    expect(isCircuitBreakerOpen("test_tool")).toBe(true);
  });

  it("resets counter on success", () => {
    for (let i = 0; i < 5; i++) {
      recordFailure("test_tool");
    }
    recordSuccess("test_tool");
    expect(isCircuitBreakerOpen("test_tool")).toBe(false);

    // Need 10 more failures now
    for (let i = 0; i < 9; i++) {
      recordFailure("test_tool");
      expect(isCircuitBreakerOpen("test_tool")).toBe(false);
    }
    recordFailure("test_tool");
    expect(isCircuitBreakerOpen("test_tool")).toBe(true);
  });

  it("tracks tools independently", () => {
    for (let i = 0; i < 10; i++) {
      recordFailure("tool_a");
    }
    expect(isCircuitBreakerOpen("tool_a")).toBe(true);
    expect(isCircuitBreakerOpen("tool_b")).toBe(false);
  });

  it("resetCircuitBreaker resets specific tool", () => {
    for (let i = 0; i < 10; i++) {
      recordFailure("tool_a");
      recordFailure("tool_b");
    }
    resetCircuitBreaker("tool_a");
    expect(isCircuitBreakerOpen("tool_a")).toBe(false);
    expect(isCircuitBreakerOpen("tool_b")).toBe(true);
  });

  it("resetAllCircuitBreakers resets everything", () => {
    for (let i = 0; i < 10; i++) {
      recordFailure("tool_a");
      recordFailure("tool_b");
    }
    resetAllCircuitBreakers();
    expect(isCircuitBreakerOpen("tool_a")).toBe(false);
    expect(isCircuitBreakerOpen("tool_b")).toBe(false);
  });

  it("success on open breaker closes it", () => {
    for (let i = 0; i < 10; i++) {
      recordFailure("test_tool");
    }
    expect(isCircuitBreakerOpen("test_tool")).toBe(true);
    recordSuccess("test_tool");
    expect(isCircuitBreakerOpen("test_tool")).toBe(false);
  });
});

// ── ToolContext extraction ───────────────────────────────

describe("extractToolContext", () => {
  it("extracts context from __agentspan_ctx__", () => {
    const inputData = {
      someArg: "value",
      __agentspan_ctx__: {
        sessionId: "sess-1",
        executionId: "wf-1",
        agentName: "my_agent",
        metadata: { key: "val" },
        dependencies: { dep: "service" },
        state: { counter: 0 },
      },
    };

    const ctx = extractToolContext(inputData);
    expect(ctx).not.toBeNull();
    expect(ctx!.sessionId).toBe("sess-1");
    expect(ctx!.executionId).toBe("wf-1");
    expect(ctx!.agentName).toBe("my_agent");
    expect(ctx!.metadata).toEqual({ key: "val" });
    expect(ctx!.dependencies).toEqual({ dep: "service" });
    expect(ctx!.state).toEqual({ counter: 0 });
  });

  it("returns null when __agentspan_ctx__ is missing", () => {
    const ctx = extractToolContext({ someArg: "value" });
    expect(ctx).toBeNull();
  });

  it("returns null when __agentspan_ctx__ is null", () => {
    const ctx = extractToolContext({ __agentspan_ctx__: null });
    expect(ctx).toBeNull();
  });

  it("creates a mutable copy of state", () => {
    const originalState = { counter: 0 };
    const inputData = {
      __agentspan_ctx__: {
        sessionId: "",
        executionId: "",
        agentName: "",
        metadata: {},
        dependencies: {},
        state: originalState,
      },
    };

    const ctx = extractToolContext(inputData);
    expect(ctx).not.toBeNull();
    ctx!.state.counter = 42;
    expect(originalState.counter).toBe(0); // Original unchanged
  });

  it("defaults missing fields to empty values", () => {
    const ctx = extractToolContext({
      __agentspan_ctx__: {},
    });
    expect(ctx).not.toBeNull();
    expect(ctx!.sessionId).toBe("");
    expect(ctx!.executionId).toBe("");
    expect(ctx!.agentName).toBe("");
    expect(ctx!.metadata).toEqual({});
    expect(ctx!.dependencies).toEqual({});
    expect(ctx!.state).toEqual({});
  });
});

// ── State mutation capture ──────────────────────────────

describe("captureStateMutations", () => {
  it("detects added keys", () => {
    const original = { a: 1 };
    const current = { a: 1, b: 2 };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ b: 2 });
  });

  it("detects modified keys", () => {
    const original = { a: 1, b: 2 };
    const current = { a: 1, b: 99 };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ b: 99 });
  });

  it("returns null when no changes", () => {
    const original = { a: 1, b: 2 };
    const current = { a: 1, b: 2 };
    const updates = captureStateMutations(original, current);
    expect(updates).toBeNull();
  });

  it("detects deep changes in nested objects", () => {
    const original = { nested: { x: 1 } };
    const current = { nested: { x: 2 } };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ nested: { x: 2 } });
  });

  it("handles empty original state", () => {
    const original = {};
    const current = { key: "value" };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ key: "value" });
  });
});

describe("appendStateUpdates", () => {
  it("merges into object result", () => {
    const result = { data: "hello" };
    const updates = { counter: 1 };
    expect(appendStateUpdates(result, updates)).toEqual({
      data: "hello",
      _state_updates: { counter: 1 },
    });
  });

  it("wraps non-object result", () => {
    const updates = { counter: 1 };
    expect(appendStateUpdates("hello", updates)).toEqual({
      result: "hello",
      _state_updates: { counter: 1 },
    });
  });

  it("wraps null result", () => {
    const updates = { counter: 1 };
    expect(appendStateUpdates(null, updates)).toEqual({
      result: null,
      _state_updates: { counter: 1 },
    });
  });

  it("wraps number result", () => {
    const updates = { key: "val" };
    expect(appendStateUpdates(42, updates)).toEqual({
      result: 42,
      _state_updates: { key: "val" },
    });
  });

  it("wraps array result", () => {
    const updates = { key: "val" };
    expect(appendStateUpdates([1, 2, 3], updates)).toEqual({
      result: [1, 2, 3],
      _state_updates: { key: "val" },
    });
  });
});

// ── Key stripping ───────────────────────────────────────

describe("stripInternalKeys", () => {
  it("removes _agent_state", () => {
    const input = { _agent_state: "internal", data: "keep" };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ data: "keep" });
    expect(result).not.toHaveProperty("_agent_state");
  });

  it("removes method", () => {
    const input = { method: "POST", data: "keep" };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ data: "keep" });
    expect(result).not.toHaveProperty("method");
  });

  it("removes __agentspan_ctx__", () => {
    const input = { __agentspan_ctx__: { id: 1 }, data: "keep" };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ data: "keep" });
    expect(result).not.toHaveProperty("__agentspan_ctx__");
  });

  it("removes all internal keys at once", () => {
    const input = {
      _agent_state: "state",
      method: "POST",
      __agentspan_ctx__: {},
      arg1: "value1",
      arg2: 42,
    };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ arg1: "value1", arg2: 42 });
  });

  it("returns copy without modifying original", () => {
    const input = { _agent_state: "state", data: "keep" };
    const result = stripInternalKeys(input);
    expect(input._agent_state).toBe("state");
    expect(result).not.toHaveProperty("_agent_state");
  });

  it("handles input with no internal keys", () => {
    const input = { arg1: "a", arg2: "b" };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ arg1: "a", arg2: "b" });
  });

  it("handles empty input", () => {
    const result = stripInternalKeys({});
    expect(result).toEqual({});
  });
});

// ── WorkerManager ────────────────────────────────────────

describe("WorkerManager", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearCredentialContext();
    resetAllCircuitBreakers();
  });

  // ── addWorker deduplication (fix #5) ───────────────────

  describe("addWorker deduplication", () => {
    it("replaces existing worker with same task name", () => {
      const manager = new WorkerManager("http://test", {}, 100);
      const handler1 = vi.fn();
      const handler2 = vi.fn();

      manager.addWorker("my_task", handler1);
      manager.addWorker("my_task", handler2);

      // Access private pendingWorkers — should have exactly 1 entry
      const workers = (manager as any).pendingWorkers;
      expect(workers).toHaveLength(1);
      expect(workers[0].handler).toBe(handler2);
    });

    it("keeps different task names as separate workers", () => {
      const manager = new WorkerManager("http://test", {}, 100);
      const handler1 = vi.fn();
      const handler2 = vi.fn();

      manager.addWorker("task_a", handler1);
      manager.addWorker("task_b", handler2);

      const workers = (manager as any).pendingWorkers;
      expect(workers).toHaveLength(2);
    });
  });

  // ── startPolling clears old pollers (fix #5) ──────────

  describe("startPolling idempotency", () => {
    it("clears existing pollers before creating new ones", async () => {
      const manager = new WorkerManager("http://test", {}, 5000);
      const handler = vi.fn();
      manager.addWorker("my_task", handler);

      // stopPolling should work even when not started
      await manager.stopPolling();

      // No taskManager after stop
      expect((manager as any).taskManager).toBeNull();
    });
  });

  // ── Credential context injection (fix #3) ─────────────
  // These tests exercise the _wrapWorker execute() callback directly
  // by accessing it through the private API, without starting the
  // full conductor polling machinery.

  describe("credential context during execution", () => {
    it("sets credential context when execution token is present", async () => {
      const serverUrl = "http://cred-test";
      const headers = { Authorization: "Bearer tok" };
      const manager = new WorkerManager(serverUrl, headers, 100);

      let contextAvailable = false;

      manager.addWorker("cred_task", async (_input) => {
        const { getCredential } = await import("../../src/credentials.js");
        try {
          await getCredential("MY_CRED");
          contextAvailable = true;
        } catch (err: unknown) {
          contextAvailable = !(
            err instanceof Error && err.message.includes("No credential context")
          );
        }
        return { ok: true };
      });

      // Mock fetch for credential resolution
      vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation(async (url: string) => {
          if (typeof url === "string" && url.includes("/credentials/resolve")) {
            return {
              ok: true,
              status: 200,
              json: async () => ({ MY_CRED: "secret-value" }),
            };
          }
          return { ok: true, status: 200, text: async () => "" };
        }),
      );

      // Get the wrapped ConductorWorker and call execute() directly
      const wrapped = (manager as any)._wrapWorker((manager as any).pendingWorkers[0]);
      await wrapped.execute({
        taskId: "task-1",
        workflowInstanceId: "wf-1",
        inputData: {
          arg1: "value",
          __agentspan_ctx__: {
            executionToken: "exec-tok-123",
            executionId: "wf-1",
          },
        },
      });

      expect(contextAvailable).toBe(true);
    });

    it("clears credential context after handler completes", async () => {
      const manager = new WorkerManager("http://test", {}, 100);

      manager.addWorker("clear_task", async () => {
        return { ok: true };
      });

      const wrapped = (manager as any)._wrapWorker((manager as any).pendingWorkers[0]);
      await wrapped.execute({
        taskId: "task-1",
        workflowInstanceId: "wf-1",
        inputData: {
          __agentspan_ctx__: {
            executionToken: "exec-tok-456",
          },
        },
      });

      const { getCredential } = await import("../../src/credentials.js");
      await expect(getCredential("ANY")).rejects.toThrow("No credential context available");
    });

    it("clears credential context even when handler throws", async () => {
      const manager = new WorkerManager("http://test", {}, 100);

      manager.addWorker("error_task", async () => {
        throw new Error("handler boom");
      });

      const wrapped = (manager as any)._wrapWorker((manager as any).pendingWorkers[0]);

      // The execute() should throw (conductor SDK catches and reports failure)
      await expect(
        wrapped.execute({
          taskId: "task-1",
          workflowInstanceId: "wf-1",
          inputData: {
            __agentspan_ctx__: {
              executionToken: "exec-tok-789",
            },
          },
        }),
      ).rejects.toThrow("handler boom");

      // Context should still be cleared despite handler error
      const { getCredential } = await import("../../src/credentials.js");
      await expect(getCredential("ANY")).rejects.toThrow("No credential context available");
    });

    it("isolates credential context across concurrent worker executions (regression: race in test_suite2)", async () => {
      // Reproduces the test_suite2_tool_calling flake deterministically:
      // The LLM emits parallel tool calls, so multiple worker.execute()
      // run concurrently. Pre-fix, all share a single module-level
      // credential context. Worker B's `finally`-block clear races with
      // worker A's getCredential() call, throwing
      // "No credential context available".
      //
      // We force the race by gating each handler on a barrier so all
      // handlers are mid-flight at the same time, then have each call
      // getCredential() and verify each got *its own* execution token's
      // resolved value back.
      const serverUrl = "http://cred-race";
      const manager = new WorkerManager(serverUrl, {}, 100);

      const NUM = 5;
      const barrier = new Promise<void>((resolve) => {
        let arrived = 0;
        manager.addWorker(
          "race_task",
          async () => {
            arrived++;
            // Wait until all handlers are running concurrently.
            if (arrived === NUM) resolve();
            await barrierGate;
            const { getCredential } = await import("../../src/credentials.js");
            return { value: await getCredential("MY_CRED") };
          },
          undefined,
        );
        // Build the gate via a sentinel resolved after all arrive.
        // The actual barrier the handlers await:
      });
      // Bridge: when `barrier` (all-arrived) resolves, open the gate.
      let openGate!: () => void;
      const barrierGate = new Promise<void>((res) => {
        openGate = res;
      });
      void barrier.then(() => openGate());

      // Echo the token back as the resolved value so we can detect crosstalk.
      vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
          if (typeof url === "string" && url.includes("/credentials/resolve")) {
            const body = JSON.parse(String(init?.body));
            return {
              ok: true,
              status: 200,
              json: async () => ({ MY_CRED: `${body.token}:resolved` }),
            };
          }
          return { ok: true, status: 200, text: async () => "" };
        }),
      );

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const wrapped = (manager as any)._wrapWorker((manager as any).pendingWorkers[0]);

      const tasks = Array.from({ length: NUM }, (_, i) => ({
        taskId: `task-${i}`,
        workflowInstanceId: "wf-1",
        inputData: {
          __agentspan_ctx__: { executionToken: `tok-${i}` },
        },
      }));

      const results = await Promise.all(tasks.map((t) => wrapped.execute(t)));

      // Each handler must see its own execution token, end to end —
      // no nulls, no crosstalk between concurrent calls.
      for (let i = 0; i < NUM; i++) {
        expect(results[i].outputData).toEqual({ value: `tok-${i}:resolved` });
      }
    });

    it("does not set credential context when no execution token", async () => {
      const manager = new WorkerManager("http://test", {}, 100);

      let handlerCalled = false;
      manager.addWorker("no_token_task", async () => {
        handlerCalled = true;
        return { ok: true };
      });

      const wrapped = (manager as any)._wrapWorker((manager as any).pendingWorkers[0]);
      await wrapped.execute({
        taskId: "task-1",
        workflowInstanceId: "wf-1",
        inputData: {
          arg1: "value",
        },
      });

      expect(handlerCalled).toBe(true);
      const { getCredential } = await import("../../src/credentials.js");
      await expect(getCredential("ANY")).rejects.toThrow("No credential context available");
    });
  });
});
