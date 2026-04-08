import { describe, it, expect } from "vitest";
import { OnToolResult, OnTextMention, OnCondition, TextGate, gate } from "../../src/handoff.js";

// ── OnToolResult ────────────────────────────────────────

describe("OnToolResult", () => {
  it("serializes to wire format", () => {
    const handoff = new OnToolResult({
      target: "analyst",
      toolName: "search",
    });
    expect(handoff.toJSON()).toEqual({
      target: "analyst",
      type: "on_tool_result",
      toolName: "search",
    });
  });

  it("includes resultContains when specified", () => {
    const handoff = new OnToolResult({
      target: "analyst",
      toolName: "search",
      resultContains: "found",
    });
    expect(handoff.toJSON()).toEqual({
      target: "analyst",
      type: "on_tool_result",
      toolName: "search",
      resultContains: "found",
    });
  });

  it("omits resultContains when not specified", () => {
    const handoff = new OnToolResult({
      target: "writer",
      toolName: "research",
    });
    const json = handoff.toJSON() as Record<string, unknown>;
    expect(json.resultContains).toBeUndefined();
  });
});

// ── OnTextMention ───────────────────────────────────────

describe("OnTextMention", () => {
  it("serializes to wire format", () => {
    const handoff = new OnTextMention({
      target: "reviewer",
      text: "TRANSFER_TO_REVIEWER",
    });
    expect(handoff.toJSON()).toEqual({
      target: "reviewer",
      type: "on_text_mention",
      text: "TRANSFER_TO_REVIEWER",
    });
  });
});

// ── OnCondition ─────────────────────────────────────────

describe("OnCondition", () => {
  it("serializes to wire format with default agent name", () => {
    const handoff = new OnCondition({
      target: "specialist",
      condition: () => true,
    });
    expect(handoff.toJSON()).toEqual({
      target: "specialist",
      type: "on_condition",
      taskName: "agent_handoff_check",
    });
  });

  it("serializes with custom agent name", () => {
    const handoff = new OnCondition({
      target: "specialist",
      condition: () => true,
      agentName: "coordinator",
    });
    expect(handoff.toJSON()).toEqual({
      target: "specialist",
      type: "on_condition",
      taskName: "coordinator_handoff_check",
    });
  });

  it("stores the condition function", () => {
    const fn = () => true;
    const handoff = new OnCondition({
      target: "target",
      condition: fn,
    });
    expect(handoff.condition).toBe(fn);
  });
});

// ── TextGate ────────────────────────────────────────────

describe("TextGate", () => {
  it("serializes to wire format", () => {
    const gate = new TextGate({ text: "APPROVED" });
    expect(gate.toJSON()).toEqual({
      type: "text_contains",
      text: "APPROVED",
      caseSensitive: false,
    });
  });

  it("supports caseSensitive option", () => {
    const g = new TextGate({ text: "APPROVED", caseSensitive: true });
    expect(g.toJSON()).toEqual({
      type: "text_contains",
      text: "APPROVED",
      caseSensitive: true,
    });
  });

  it("defaults caseSensitive to false", () => {
    const g = new TextGate({ text: "test" });
    expect(g.caseSensitive).toBe(false);
  });
});

// ── gate() ──────────────────────────────────────────────

describe("gate()", () => {
  it("returns taskName and fn for custom gate", () => {
    const fn = () => true;
    const result = gate(fn);
    expect(result.taskName).toBe("agent_gate");
    expect(result.fn).toBe(fn);
  });

  it("uses custom agent name in taskName", () => {
    const fn = () => true;
    const result = gate(fn, { agentName: "my_agent" });
    expect(result.taskName).toBe("my_agent_gate");
    expect(result.fn).toBe(fn);
  });
});
