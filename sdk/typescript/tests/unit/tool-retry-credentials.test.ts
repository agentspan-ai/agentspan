// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * Unit tests for credentials serialization in serializeTool() — PR #159 / Issue #150.
 *
 * Covers:
 *   - String credentials merged into config.config.credentials
 *   - CredentialFile objects excluded from config.config.credentials
 *   - Coexistence of credentials + retry fields (non-destructive spread-merge)
 *   - httpTool credentials path
 *
 * Pure unit tests — no server, no mocks, no network.
 */

import { describe, it, expect } from "vitest";
import { tool, getToolDef, httpTool } from "../../src/tool.js";
import { AgentConfigSerializer } from "../../src/serializer.js";
import type { RetryLogic } from "../../src/types.js";
import type { CredentialFile } from "../../src/types.js";

const serializer = new AgentConfigSerializer();

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWorkerTool(opts: {
  credentials?: (string | CredentialFile)[];
  retryCount?: number;
  retryDelaySeconds?: number;
  retryLogic?: RetryLogic;
}) {
  return tool(async (_args: { x: string }) => "ok", {
    name: "my_tool",
    description: "A test tool.",
    inputSchema: { type: "object", properties: { x: { type: "string" } } },
    ...(opts.credentials !== undefined && { credentials: opts.credentials }),
    ...(opts.retryCount !== undefined && { retryCount: opts.retryCount }),
    ...(opts.retryDelaySeconds !== undefined && {
      retryDelaySeconds: opts.retryDelaySeconds,
    }),
    ...(opts.retryLogic !== undefined && { retryLogic: opts.retryLogic }),
  });
}

// ── AgentConfigSerializer.serializeTool() — credentials in config ─────────────

describe("AgentConfigSerializer.serializeTool() — credentials in config", () => {
  it("emits credentials into config.config for a worker tool", () => {
    const t = makeWorkerTool({ credentials: ["MY_KEY"] });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    expect(result.config).toBeDefined();
    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["MY_KEY"]);
  });

  it("emits multiple credentials into config.config", () => {
    const t = makeWorkerTool({ credentials: ["KEY_A", "KEY_B"] });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["KEY_A", "KEY_B"]);
  });

  it("omits credentials key from config when credentials array is empty", () => {
    const t = makeWorkerTool({ credentials: [] });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = (result.config ?? {}) as Record<string, unknown>;
    expect(config).not.toHaveProperty("credentials");
  });

  it("omits credentials key from config when credentials is undefined", () => {
    const t = makeWorkerTool({});
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = (result.config ?? {}) as Record<string, unknown>;
    expect(config).not.toHaveProperty("credentials");
  });

  it("excludes CredentialFile objects from config.credentials", () => {
    const credFile: CredentialFile = {
      envVar: "KUBECONFIG",
      relativePath: ".kube/config",
    };
    const t = makeWorkerTool({ credentials: [credFile] });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = (result.config ?? {}) as Record<string, unknown>;
    expect(config).not.toHaveProperty("credentials");
  });

  it("includes only string credentials when mixed with CredentialFile", () => {
    const credFile: CredentialFile = { envVar: "KUBECONFIG" };
    const t = makeWorkerTool({ credentials: ["API_KEY", credFile] });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["API_KEY"]);
  });

  it("credentials-only tool has no retry keys in config", () => {
    const t = makeWorkerTool({ credentials: ["MY_KEY"] });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["MY_KEY"]);
    expect(config).not.toHaveProperty("retryCount");
    expect(config).not.toHaveProperty("retryDelaySeconds");
    expect(config).not.toHaveProperty("retryLogic");
  });
});

// ── AgentConfigSerializer.serializeTool() — retry + credentials coexistence ───

describe("AgentConfigSerializer.serializeTool() — retry fields + credentials coexistence", () => {
  it("credentials do not overwrite pre-existing config keys", () => {
    const t = httpTool({
      name: "api_call",
      description: "Call API",
      url: "https://api.example.com",
      method: "POST",
      credentials: ["API_KEY"],
    });
    const result = serializer.serializeTool(t);

    const config = result.config as Record<string, unknown>;
    expect(config.url).toBe("https://api.example.com");
    expect(config.method).toBe("POST");
    expect(config.credentials).toEqual(["API_KEY"]);
  });

  it("retry fields do not overwrite credentials in config", () => {
    const t = makeWorkerTool({ credentials: ["K"], retryCount: 3 });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["K"]);
    expect(config.retryCount).toBe(3);
  });

  it("all three retry fields plus credentials all coexist", () => {
    const t = makeWorkerTool({
      credentials: ["X", "Y"],
      retryCount: 5,
      retryDelaySeconds: 10,
      retryLogic: "EXPONENTIAL_BACKOFF",
    });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["X", "Y"]);
    expect(config.retryCount).toBe(5);
    expect(config.retryDelaySeconds).toBe(10);
    expect(config.retryLogic).toBe("EXPONENTIAL_BACKOFF");
  });

  it("retryCount=0 coexists with credentials", () => {
    const t = makeWorkerTool({ credentials: ["K"], retryCount: 0 });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    // retryCount=0 must NOT be skipped as falsy
    expect(config.retryCount).toBe(0);
    expect(config.retryCount).not.toBeUndefined();
    expect(config.credentials).toEqual(["K"]);
  });

  it("coexists with credentials in config (retryCount + retryLogic + credentials)", () => {
    const t = makeWorkerTool({
      retryCount: 2,
      retryLogic: "LINEAR_BACKOFF",
      credentials: ["MY_API_KEY"],
    });
    const def = getToolDef(t);
    const result = serializer.serializeTool(def);

    const config = result.config as Record<string, unknown>;
    expect(config.retryCount).toBe(2);
    expect(config.retryLogic).toBe("LINEAR_BACKOFF");
    expect(config.credentials).toEqual(["MY_API_KEY"]);
  });
});

// ── AgentConfigSerializer.serializeTool() — httpTool credentials ──────────────

describe("AgentConfigSerializer.serializeTool() — httpTool credentials", () => {
  it("httpTool with credentials emits credentials inside config", () => {
    const t = httpTool({
      name: "api_call",
      description: "Call API",
      url: "https://api.example.com",
      method: "GET",
      credentials: ["API_KEY"],
    });
    const result = serializer.serializeTool(t);

    const config = result.config as Record<string, unknown>;
    expect(config.credentials).toEqual(["API_KEY"]);
    // Pre-existing config keys must survive
    expect(config.url).toBe("https://api.example.com");
  });

  it("httpTool without credentials has no credentials key in config", () => {
    const t = httpTool({
      name: "api_call",
      description: "Call API",
      url: "https://api.example.com",
      method: "GET",
    });
    const result = serializer.serializeTool(t);

    const config = (result.config ?? {}) as Record<string, unknown>;
    expect(config).not.toHaveProperty("credentials");
  });
});
