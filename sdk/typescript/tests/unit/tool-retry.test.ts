// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * Unit tests for retry configuration on the tool() function (issue #150).
 *
 * These are pure unit tests — no server, no mocks, just verifying the
 * ToolDef wiring and serializer output.
 */

import { describe, it, expect } from "vitest";
import { tool, getToolDef, Tool, toolsFrom } from "../../src/tool.js";
import { AgentConfigSerializer } from "../../src/serializer.js";
import type { RetryLogic } from "../../src/types.js";

const serializer = new AgentConfigSerializer();

// ── tool() decorator tests ────────────────────────────────────────────────────

describe("tool() — retry fields", () => {
  it("leaves retryCount/retryDelaySeconds/retryLogic undefined when not set", () => {
    const myTool = tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A simple tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
    });

    const def = getToolDef(myTool);
    expect(def.retryCount).toBeUndefined();
    expect(def.retryDelaySeconds).toBeUndefined();
    expect(def.retryLogic).toBeUndefined();
  });

  it("stores retryCount on ToolDef", () => {
    const myTool = tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A simple tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
      retryCount: 10,
    });

    const def = getToolDef(myTool);
    expect(def.retryCount).toBe(10);
    expect(def.retryDelaySeconds).toBeUndefined();
    expect(def.retryLogic).toBeUndefined();
  });

  it("stores retryDelaySeconds on ToolDef", () => {
    const myTool = tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A simple tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
      retryDelaySeconds: 5,
    });

    const def = getToolDef(myTool);
    expect(def.retryCount).toBeUndefined();
    expect(def.retryDelaySeconds).toBe(5);
    expect(def.retryLogic).toBeUndefined();
  });

  it("stores retryLogic on ToolDef", () => {
    const myTool = tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A simple tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
      retryLogic: "EXPONENTIAL_BACKOFF",
    });

    const def = getToolDef(myTool);
    expect(def.retryCount).toBeUndefined();
    expect(def.retryDelaySeconds).toBeUndefined();
    expect(def.retryLogic).toBe("EXPONENTIAL_BACKOFF");
  });

  it("stores retryCount=0 (not undefined — zero means no retries)", () => {
    const myTool = tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A simple tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
      retryCount: 0,
    });

    const def = getToolDef(myTool);
    expect(def.retryCount).toBe(0);
    expect(def.retryCount).not.toBeUndefined();
  });

  it("stores all three retry params when all are set", () => {
    const myTool = tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A simple tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
      retryCount: 5,
      retryDelaySeconds: 10,
      retryLogic: "FIXED",
    });

    const def = getToolDef(myTool);
    expect(def.retryCount).toBe(5);
    expect(def.retryDelaySeconds).toBe(10);
    expect(def.retryLogic).toBe("FIXED");
  });

  it("accepts all three RetryLogic values", () => {
    const values: RetryLogic[] = ["FIXED", "LINEAR_BACKOFF", "EXPONENTIAL_BACKOFF"];
    for (const logic of values) {
      const myTool = tool(async (_args: { x: string }) => "ok", {
        name: "my_tool",
        description: "A simple tool.",
        inputSchema: { type: "object", properties: { x: { type: "string" } } },
        retryLogic: logic,
      });
      expect(getToolDef(myTool).retryLogic).toBe(logic);
    }
  });
});

// ── @Tool class decorator tests ───────────────────────────────────────────────

describe("@Tool decorator — retry fields", () => {
  it("passes retry fields through toolsFrom()", () => {
    class MyTools {
      @Tool({
        name: "my_tool",
        description: "A tool with retry config.",
        inputSchema: { type: "object", properties: { x: { type: "string" } } },
        retryCount: 3,
        retryDelaySeconds: 7,
        retryLogic: "LINEAR_BACKOFF",
      })
      async myMethod(_args: { x: string }): Promise<string> {
        return "ok";
      }
    }

    const instance = new MyTools();
    const tools = toolsFrom(instance);
    expect(tools).toHaveLength(1);

    const def = getToolDef(tools[0]);
    expect(def.retryCount).toBe(3);
    expect(def.retryDelaySeconds).toBe(7);
    expect(def.retryLogic).toBe("LINEAR_BACKOFF");
  });

  it("leaves retry fields undefined when not set in @Tool", () => {
    class MyTools {
      @Tool({
        name: "my_tool",
        description: "A tool without retry config.",
        inputSchema: { type: "object", properties: {} },
      })
      async myMethod(_args: unknown): Promise<string> {
        return "ok";
      }
    }

    const instance = new MyTools();
    const tools = toolsFrom(instance);
    const def = getToolDef(tools[0]);
    expect(def.retryCount).toBeUndefined();
    expect(def.retryDelaySeconds).toBeUndefined();
    expect(def.retryLogic).toBeUndefined();
  });
});

// ── getToolDef() raw ToolDef passthrough tests ────────────────────────────────

describe("getToolDef() — raw ToolDef passthrough", () => {
  it("passes retry fields through from a raw ToolDef object", () => {
    const raw = {
      name: "my_tool",
      description: "A tool.",
      inputSchema: { type: "object", properties: {} },
      toolType: "worker" as const,
      retryCount: 4,
      retryDelaySeconds: 8,
      retryLogic: "EXPONENTIAL_BACKOFF" as RetryLogic,
    };

    const def = getToolDef(raw);
    expect(def.retryCount).toBe(4);
    expect(def.retryDelaySeconds).toBe(8);
    expect(def.retryLogic).toBe("EXPONENTIAL_BACKOFF");
  });

  it("leaves retry fields undefined when absent from raw ToolDef", () => {
    const raw = {
      name: "my_tool",
      description: "A tool.",
      inputSchema: { type: "object", properties: {} },
    };

    const def = getToolDef(raw);
    expect(def.retryCount).toBeUndefined();
    expect(def.retryDelaySeconds).toBeUndefined();
    expect(def.retryLogic).toBeUndefined();
  });
});

// ── AgentConfigSerializer.serializeTool() tests ───────────────────────────────

describe("AgentConfigSerializer.serializeTool() — retry fields", () => {
  function makeWorkerTool(
    retryCount?: number,
    retryDelaySeconds?: number,
    retryLogic?: RetryLogic,
    credentials?: string[],
  ) {
    return tool(async (_args: { x: string }) => "ok", {
      name: "my_tool",
      description: "A test tool.",
      inputSchema: { type: "object", properties: { x: { type: "string" } } },
      ...(retryCount !== undefined && { retryCount }),
      ...(retryDelaySeconds !== undefined && { retryDelaySeconds }),
      ...(retryLogic !== undefined && { retryLogic }),
      ...(credentials !== undefined && { credentials }),
    });
  }

  it("emits retryCount/retryDelaySeconds/retryLogic in config when all are set", () => {
    const t = makeWorkerTool(5, 10, "FIXED");
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    expect(result.config).toBeDefined();
    const config = result.config as Record<string, unknown>;
    expect(config.retryCount).toBe(5);
    expect(config.retryDelaySeconds).toBe(10);
    expect(config.retryLogic).toBe("FIXED");
  });

  it("omits retry keys from config when all retry fields are undefined", () => {
    const t = makeWorkerTool();
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = (result.config ?? {}) as Record<string, unknown>;
    expect(config).not.toHaveProperty("retryCount");
    expect(config).not.toHaveProperty("retryDelaySeconds");
    expect(config).not.toHaveProperty("retryLogic");
  });

  it("emits only retryCount when only retryCount is set", () => {
    const t = makeWorkerTool(3);
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.retryCount).toBe(3);
    expect(config).not.toHaveProperty("retryDelaySeconds");
    expect(config).not.toHaveProperty("retryLogic");
  });

  it("includes retryCount=0 in config (not skipped as falsy)", () => {
    const t = makeWorkerTool(0);
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.retryCount).toBe(0);
  });

  it("coexists with credentials in config", () => {
    const t = makeWorkerTool(2, undefined, "LINEAR_BACKOFF", ["MY_API_KEY"]);
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.retryCount).toBe(2);
    expect(config.retryLogic).toBe("LINEAR_BACKOFF");
    expect(config.credentials).toEqual(["MY_API_KEY"]);
  });

  it("emits retryLogic=LINEAR_BACKOFF correctly", () => {
    const t = makeWorkerTool(undefined, undefined, "LINEAR_BACKOFF");
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.retryLogic).toBe("LINEAR_BACKOFF");
  });

  it("emits retryLogic=EXPONENTIAL_BACKOFF correctly", () => {
    const t = makeWorkerTool(undefined, undefined, "EXPONENTIAL_BACKOFF");
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.retryLogic).toBe("EXPONENTIAL_BACKOFF");
  });
});
