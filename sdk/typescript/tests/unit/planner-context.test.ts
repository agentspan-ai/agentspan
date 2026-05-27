// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// TypeScript SDK mirror of sdk/python/tests/unit/test_planner_context.py.
// Pins Agent's plannerContext normalisation + AgentConfigSerializer's wire
// emission. Same shape, same wire format — guarantees the four SDKs stay
// in lock-step on this feature.

import { describe, it, expect } from "vitest";
import { Agent } from "../../src/agent.js";
import { Context } from "../../src/plans.js";
import { tool } from "../../src/tool.js";
import { AgentConfigSerializer } from "../../src/serializer.js";

const stubTool = tool(async (args: { x: string }) => args.x, {
  name: "stub_tool",
  description: "Stub for tests",
});

function planner(): Agent {
  return new Agent({ name: "planner_sub", instructions: "plan it" });
}

const serializer = new AgentConfigSerializer();

describe("Agent.plannerContext normalisation", () => {
  it("bare strings auto-wrap to Context(text=...)", () => {
    const a = new Agent({
      name: "h",
      strategy: "plan_execute",
      planner: planner(),
      tools: [stubTool],
      plannerContext: ["rule one", "rule two"],
    });
    expect(a.plannerContext).toBeDefined();
    expect(a.plannerContext!.length).toBe(2);
    a.plannerContext!.forEach((c) => expect(c).toBeInstanceOf(Context));
    expect((a.plannerContext![0] as Context).text).toBe("rule one");
    expect((a.plannerContext![1] as Context).text).toBe("rule two");
  });

  it("mixed strings and Context objects", () => {
    const a = new Agent({
      name: "h",
      strategy: "plan_execute",
      planner: planner(),
      tools: [stubTool],
      plannerContext: [
        "inline rule",
        new Context({ url: "https://x/y", headers: { "X-Auth": "abc" } }),
      ],
    });
    expect((a.plannerContext![0] as Context).text).toBe("inline rule");
    expect((a.plannerContext![1] as Context).url).toBe("https://x/y");
  });

  it("dict entries pass through unchanged", () => {
    // Hand-rolled wire-shape dicts — matches planSource's typing for
    // power users who want to bypass the typed wrapper.
    const wire = { url: "https://x/y", required: false };
    const a = new Agent({
      name: "h",
      strategy: "plan_execute",
      planner: planner(),
      tools: [stubTool],
      plannerContext: [wire],
    });
    expect(a.plannerContext).toEqual([wire]);
  });

  it("rejects plannerContext on non-PLAN_EXECUTE strategy", () => {
    // Same guard shape as planner=/fallback=. Setting plannerContext on
    // anything other than PLAN_EXECUTE is a silent bug — reject loudly.
    expect(
      () =>
        new Agent({
          name: "h",
          strategy: "handoff",
          agents: [planner()],
          plannerContext: ["rule"],
        }),
    ).toThrow(/plannerContext.*only valid with strategy='plan_execute'/);
  });

  it("undefined plannerContext leaves field undefined", () => {
    const a = new Agent({
      name: "h",
      strategy: "plan_execute",
      planner: planner(),
      tools: [stubTool],
    });
    expect(a.plannerContext).toBeUndefined();
  });
});

describe("AgentConfigSerializer plannerContext", () => {
  it("omits plannerContext when not set (counterfactual)", () => {
    // Without this, the positive test below could be vacuously true if
    // the serializer always emitted the field.
    const a = new Agent({
      name: "h",
      strategy: "plan_execute",
      planner: planner(),
      tools: [stubTool],
    });
    const cfg = serializer.serializeAgent(a);
    expect(cfg).not.toHaveProperty("plannerContext");
  });

  it("emits plannerContext with text + url entries", () => {
    const a = new Agent({
      name: "h",
      strategy: "plan_execute",
      planner: planner(),
      tools: [stubTool],
      plannerContext: [
        "inline rule",
        new Context({
          url: "https://confluence.example.com/onboarding",
          headers: { Authorization: "Bearer ${CONFLUENCE_TOKEN}" },
          required: false,
          maxBytes: 8192,
        }),
      ],
    });
    const cfg = serializer.serializeAgent(a);
    expect(cfg.plannerContext).toEqual([
      { text: "inline rule" },
      {
        url: "https://confluence.example.com/onboarding",
        headers: { Authorization: "Bearer ${CONFLUENCE_TOKEN}" },
        required: false,
        maxBytes: 8192,
      },
    ]);
  });
});
