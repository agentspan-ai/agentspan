import { describe, expect, it } from "vitest";

import { inferSubAgentStrategy, mapTaskStatus, pacAgentRole } from "../agentExecutionUtils";
import { AgentStatus, AgentStrategy } from "../types";

describe("mapTaskStatus", () => {
  it("maps COMPLETED to COMPLETED", () => {
    expect(mapTaskStatus("COMPLETED")).toBe(AgentStatus.COMPLETED);
  });

  it("maps FAILED to FAILED", () => {
    expect(mapTaskStatus("FAILED")).toBe(AgentStatus.FAILED);
  });

  it("maps IN_PROGRESS to RUNNING", () => {
    expect(mapTaskStatus("IN_PROGRESS")).toBe(AgentStatus.RUNNING);
  });

  // Reproduces the bug from execution d0f322e8-e332-4919-9d1a-3664ee5b9728:
  // a SUB_WORKFLOW task on PAC's optional:true plan-exec branch carries
  // status COMPLETED_WITH_ERRORS when the underlying sub-workflow failed.
  // Before the fix this fell through to the default RUNNING case and the
  // UI rendered a misleading orange "running" badge for the failed plan.
  it("maps COMPLETED_WITH_ERRORS to FAILED", () => {
    expect(mapTaskStatus("COMPLETED_WITH_ERRORS")).toBe(AgentStatus.FAILED);
  });

  it("maps other terminal-failure statuses to FAILED", () => {
    expect(mapTaskStatus("FAILED_WITH_TERMINAL_ERROR")).toBe(AgentStatus.FAILED);
    expect(mapTaskStatus("TIMED_OUT")).toBe(AgentStatus.FAILED);
    expect(mapTaskStatus("CANCELED")).toBe(AgentStatus.FAILED);
  });

  it("maps SCHEDULED to RUNNING", () => {
    expect(mapTaskStatus("SCHEDULED")).toBe(AgentStatus.RUNNING);
  });

  it("falls back to RUNNING for unknown statuses", () => {
    expect(mapTaskStatus("BANANA")).toBe(AgentStatus.RUNNING);
  });
});

describe("inferSubAgentStrategy", () => {
  // PLAN_EXECUTE produces three top-level SUB_WORKFLOWs (planner →
  // plan_exec → fallback) that run sequentially. Before the fix the
  // transform tagged any group of length > 1 as PARALLEL, which made
  // the diagram lay out chronologically-disjoint agents side-by-side.
  it("returns SEQUENTIAL for chronologically disjoint agents (PAE shape)", () => {
    const subAgents = [
      { startTime: 1000, endTime: 1100 }, // planner
      { startTime: 1100, endTime: 1110 }, // plan_exec (failed instantly)
      { startTime: 1200, endTime: 2200 }, // fallback
    ];
    expect(inferSubAgentStrategy(subAgents)).toBe(AgentStrategy.SEQUENTIAL);
  });

  it("returns PARALLEL when intervals overlap", () => {
    const subAgents = [
      { startTime: 1000, endTime: 2000 },
      { startTime: 1500, endTime: 2500 }, // starts before [0] ends
      { startTime: 1700, endTime: 3000 },
    ];
    expect(inferSubAgentStrategy(subAgents)).toBe(AgentStrategy.PARALLEL);
  });

  it("returns PARALLEL even if only one pair overlaps", () => {
    const subAgents = [
      { startTime: 1000, endTime: 1100 },
      { startTime: 1100, endTime: 1200 }, // sequential w/ [0]
      { startTime: 1150, endTime: 1300 }, // overlaps [1]
    ];
    expect(inferSubAgentStrategy(subAgents)).toBe(AgentStrategy.PARALLEL);
  });

  it("returns SEQUENTIAL for a single agent", () => {
    expect(inferSubAgentStrategy([{ startTime: 1000, endTime: 2000 }]))
      .toBe(AgentStrategy.SEQUENTIAL);
  });

  it("returns SEQUENTIAL for empty input", () => {
    expect(inferSubAgentStrategy([])).toBe(AgentStrategy.SEQUENTIAL);
  });

  it("falls back to PARALLEL when any agent is missing timestamps", () => {
    const subAgents = [
      { startTime: 1000, endTime: 1100 },
      { startTime: undefined, endTime: undefined },
    ];
    expect(inferSubAgentStrategy(subAgents)).toBe(AgentStrategy.PARALLEL);
  });

  // 5ms tolerance absorbs clock jitter — two branches that finish a few
  // ms apart with a tiny start-time overlap still read as sequential to
  // a human, so call them sequential in the UI too.
  it("treats sub-ms overlap within tolerance as SEQUENTIAL", () => {
    const subAgents = [
      { startTime: 1000, endTime: 1100 },
      { startTime: 1098, endTime: 1200 }, // 2ms overlap, under 5ms tolerance
    ];
    expect(inferSubAgentStrategy(subAgents)).toBe(AgentStrategy.SEQUENTIAL);
  });

  // Falls back to event timestamps when the agent itself doesn't carry
  // start/end fields (nested cases).
  it("derives intervals from event timestamps when agent fields are missing", () => {
    const subAgents = [
      {
        turns: [{ events: [{ timestamp: 1000 }, { timestamp: 1100 }] }],
      },
      {
        turns: [{ events: [{ timestamp: 1200 }, { timestamp: 1300 }] }],
      },
    ];
    expect(inferSubAgentStrategy(subAgents)).toBe(AgentStrategy.SEQUENTIAL);
  });
});

describe("pacAgentRole", () => {
  // Server-side conventions emitted by MultiAgentCompiler.compilePlanExecute
  // and planWorkflowName. These names are stable; we own both sides.

  it("recognises the planner suffix", () => {
    expect(pacAgentRole("guardrails_demo_planner")).toEqual({ role: "Plan", display: "Planner" });
    expect(pacAgentRole("coder_planner")).toEqual({ role: "Plan", display: "Planner" });
  });

  it("recognises the compiled-plan workflow name (pe_<harness>_plan)", () => {
    expect(pacAgentRole("pe_guardrails_demo_plan")).toEqual({ role: "Execute", display: "Execute" });
    expect(pacAgentRole("pe_coder_plan")).toEqual({ role: "Execute", display: "Execute" });
  });

  it("recognises all fallback variants", () => {
    expect(pacAgentRole("guardrails_demo_fallback")).toEqual({ role: "Fallback", display: "Fallback" });
    expect(pacAgentRole("guardrails_demo_compile_fallback")).toEqual({ role: "Fallback", display: "Fallback" });
    expect(pacAgentRole("guardrails_demo_noplan_fallback")).toEqual({ role: "Fallback", display: "Fallback" });
  });

  it("returns null for non-PAE agents", () => {
    expect(pacAgentRole("just_some_agent")).toBeNull();
    expect(pacAgentRole("plannerlike_but_not")).toBeNull();
    expect(pacAgentRole("")).toBeNull();
    expect(pacAgentRole(null)).toBeNull();
    expect(pacAgentRole(undefined)).toBeNull();
  });

  it("does not match agents that merely contain the suffix in the middle", () => {
    expect(pacAgentRole("planner_helper")).toBeNull(); // doesn't END in _planner
    expect(pacAgentRole("just_pe_plan")).toBeNull();   // doesn't START with pe_
    expect(pacAgentRole("pe_plan")).toBeNull();        // pe_ + _plan with empty middle isn't a real harness name
  });
});
