/**
 * 03 — Multi-Agent Strategy Tests
 *
 * Test orchestration strategies: handoff, sequential, parallel, router.
 * Each section scripts the expected event sequences using MockEvent.
 *
 * Covers:
 *   - Handoff — parent delegates to the right specialist
 *   - Sequential pipeline — agents run in order
 *   - Parallel execution — all agents must run
 *   - Router — dedicated planner picks one agent
 *   - assertHandoffTo / assertAgentRan / validateStrategy
 *
 * Run:
 *   npx vitest run examples/mock_tests/03-multi-agent-strategies.test.ts
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import { Agent, tool } from "@agentspan-ai/sdk";
import {
  MockEvent,
  mockRun,
  expect as agentExpect,
  assertAgentRan,
  assertHandoffTo,
  assertToolUsed,
  assertNoErrors,
  assertStatus,
  validateStrategy,
} from "@agentspan-ai/sdk/testing";

// ── Tools ────────────────────────────────────────────────────────────

const searchDocs = tool(
  async (args: { query: string }) => `Documentation for: ${args.query}`,
  {
    name: "search_docs",
    description: "Search documentation.",
    inputSchema: z.object({ query: z.string() }),
  },
);

const runQuery = tool(
  async (args: { sql: string }) => [{ id: 1, name: "result" }],
  {
    name: "run_query",
    description: "Execute a database query.",
    inputSchema: z.object({ sql: z.string() }),
  },
);

// ═════════════════════════════════════════════════════════════════════
// 1. HANDOFF — parent picks the right specialist
// ═════════════════════════════════════════════════════════════════════

const docsAgent = new Agent({
  name: "docs-specialist",
  model: "openai/gpt-4o",
  instructions: "Answer documentation questions.",
  tools: [searchDocs],
});

const dbAgent = new Agent({
  name: "db-specialist",
  model: "openai/gpt-4o",
  instructions: "Answer database questions.",
  tools: [runQuery],
});

const triageAgent = new Agent({
  name: "triage",
  model: "openai/gpt-4o",
  instructions: "Route questions to the right specialist.",
  agents: [docsAgent, dbAgent],
  strategy: "handoff",
});

describe("Handoff Strategy", () => {
  it("routes docs question to docs specialist", () => {
    const result = mockRun(triageAgent, "How do I configure logging?", {
      events: [
        MockEvent.handoff("docs-specialist"),
        MockEvent.toolCall("search_docs", { query: "configure logging" }),
        MockEvent.toolResult("search_docs", "Set LOG_LEVEL=debug in your config."),
        MockEvent.done({ result: "Set LOG_LEVEL=debug in your config." }),
      ],
    });

    assertHandoffTo(result, "docs-specialist");
    assertToolUsed(result, "search_docs");
    assertNoErrors(result);
  });

  it("db specialist runs its tool when targeted directly", () => {
    const result = mockRun(dbAgent, "How many users signed up today?", {
      events: [
        MockEvent.toolCall("run_query", { sql: "SELECT COUNT(*) FROM users WHERE created_at = CURRENT_DATE" }),
        MockEvent.toolResult("run_query", [{ count: 150 }]),
        MockEvent.done({ result: "150 users signed up today." }),
      ],
    });

    assertToolUsed(result, "run_query");
    assertNoErrors(result);
  });

  it("triage agent produces handoff event", () => {
    const result = mockRun(triageAgent, "Show me the user table schema", {
      events: [
        MockEvent.handoff("db-specialist"),
        MockEvent.toolCall("run_query", { sql: "DESCRIBE users" }),
        MockEvent.toolResult("run_query", [{ col: "id" }, { col: "name" }]),
        MockEvent.done({ result: "User table has columns: id, name." }),
      ],
    });

    assertHandoffTo(result, "db-specialist");
    agentExpect(result).completed();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 2. SEQUENTIAL — agents run in order
// ═════════════════════════════════════════════════════════════════════

const researcher = new Agent({
  name: "researcher",
  model: "openai/gpt-4o",
  instructions: "Research the topic thoroughly.",
  tools: [searchDocs],
});

const drafter = new Agent({
  name: "drafter",
  model: "openai/gpt-4o",
  instructions: "Write a draft based on the research.",
});

const reviewer = new Agent({
  name: "reviewer",
  model: "openai/gpt-4o",
  instructions: "Review and polish the draft.",
});

const contentPipeline = new Agent({
  name: "content-pipeline",
  model: "openai/gpt-4o",
  agents: [researcher, drafter, reviewer],
  strategy: "sequential",
});

describe("Sequential Strategy", () => {
  it("runs all agents in order", () => {
    const result = mockRun(contentPipeline, "Write a guide on API testing", {
      events: [
        MockEvent.handoff("researcher"),
        MockEvent.toolCall("search_docs", { query: "API testing" }),
        MockEvent.toolResult("search_docs", "API testing best practices..."),
        MockEvent.handoff("drafter"),
        MockEvent.handoff("reviewer"),
        MockEvent.done({ result: "API testing guide completed." }),
      ],
    });

    assertAgentRan(result, "researcher");
    assertAgentRan(result, "drafter");
    assertAgentRan(result, "reviewer");
    assertNoErrors(result);
  });

  it("researcher uses search tool before drafter runs", () => {
    const result = mockRun(contentPipeline, "Write about microservices", {
      events: [
        MockEvent.handoff("researcher"),
        MockEvent.toolCall("search_docs", { query: "microservices" }),
        MockEvent.toolResult("search_docs", "Microservices patterns..."),
        MockEvent.handoff("drafter"),
        MockEvent.handoff("reviewer"),
        MockEvent.done({ result: "Microservices guide completed." }),
      ],
    });

    assertToolUsed(result, "search_docs");
    // Verify search happens before drafter's handoff
    const events = result.events;
    const searchIdx = events.findIndex(
      (e) => e.type === "tool_call" && e.toolName === "search_docs",
    );
    const drafterIdx = events.findIndex(
      (e) => e.type === "handoff" && e.target === "drafter",
    );
    expect(searchIdx).toBeLessThan(drafterIdx);
  });

  it("validates sequential strategy against trace", () => {
    const result = mockRun(contentPipeline, "Write something", {
      events: [
        MockEvent.handoff("researcher"),
        MockEvent.handoff("drafter"),
        MockEvent.handoff("reviewer"),
        MockEvent.done({ result: "Done." }),
      ],
    });

    expect(() => validateStrategy(contentPipeline, result)).not.toThrow();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 3. PARALLEL — all agents run concurrently
// ═════════════════════════════════════════════════════════════════════

const securityAuditor = new Agent({
  name: "security-auditor",
  model: "openai/gpt-4o",
  instructions: "Audit for security vulnerabilities.",
});

const performanceAuditor = new Agent({
  name: "performance-auditor",
  model: "openai/gpt-4o",
  instructions: "Audit for performance bottlenecks.",
});

const accessibilityAuditor = new Agent({
  name: "accessibility-auditor",
  model: "openai/gpt-4o",
  instructions: "Audit for accessibility compliance.",
});

const auditTeam = new Agent({
  name: "audit-team",
  model: "openai/gpt-4o",
  agents: [securityAuditor, performanceAuditor, accessibilityAuditor],
  strategy: "parallel",
});

describe("Parallel Strategy", () => {
  it("all auditors run", () => {
    const result = mockRun(auditTeam, "Audit the checkout page", {
      events: [
        MockEvent.handoff("security-auditor"),
        MockEvent.handoff("performance-auditor"),
        MockEvent.handoff("accessibility-auditor"),
        MockEvent.done({ result: "Audit complete." }),
      ],
    });

    assertAgentRan(result, "security-auditor");
    assertAgentRan(result, "performance-auditor");
    assertAgentRan(result, "accessibility-auditor");
    assertNoErrors(result);
  });

  it("validates parallel strategy against trace", () => {
    const result = mockRun(auditTeam, "Audit the dashboard", {
      events: [
        MockEvent.handoff("security-auditor"),
        MockEvent.handoff("performance-auditor"),
        MockEvent.handoff("accessibility-auditor"),
        MockEvent.done({ result: "All perspectives covered." }),
      ],
    });

    agentExpect(result).completed();
    expect(() => validateStrategy(auditTeam, result)).not.toThrow();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 4. ROUTER — dedicated planner picks one specialist
// ═════════════════════════════════════════════════════════════════════

const backendDev = new Agent({
  name: "backend",
  model: "openai/gpt-4o",
  instructions: "Fix backend/API bugs.",
  tools: [runQuery],
});

const frontendDev = new Agent({
  name: "frontend",
  model: "openai/gpt-4o",
  instructions: "Fix frontend/UI bugs.",
});

const planner = new Agent({
  name: "planner",
  model: "openai/gpt-4o",
  instructions: "Route bugs to backend or frontend.",
});

const bugTriage = new Agent({
  name: "bug-triage",
  model: "openai/gpt-4o",
  agents: [backendDev, frontendDev],
  strategy: "router",
  router: planner,
});

describe("Router Strategy", () => {
  it("routes to a sub-agent via the router", () => {
    const result = mockRun(bugTriage, "The /users endpoint returns 500", {
      events: [
        MockEvent.handoff("backend"),
        MockEvent.toolCall("run_query", { sql: "SHOW ERRORS" }),
        MockEvent.toolResult("run_query", [{ error: "null pointer" }]),
        MockEvent.done({ result: "Found null pointer error in /users endpoint." }),
      ],
    });

    assertHandoffTo(result, "backend");
    assertToolUsed(result, "run_query");
  });

  it("completes successfully with router strategy", () => {
    const result = mockRun(bugTriage, "The submit button is invisible on mobile", {
      events: [
        MockEvent.handoff("frontend"),
        MockEvent.done({ result: "Fixed CSS visibility issue." }),
      ],
    });

    agentExpect(result).completed();
    assertHandoffTo(result, "frontend");
  });
});
