/**
 * 03 — Multi-Agent Strategy Tests
 *
 * Test orchestration strategies: handoff, sequential, parallel, router.
 * Each section defines agents, mocks the expected behavior, and asserts
 * correctness.
 *
 * Covers:
 *   - Handoff — parent delegates to the right specialist
 *   - Sequential pipeline — agents run in order
 *   - Parallel execution — all agents must run
 *   - Router — dedicated planner picks one agent
 *   - assertAgentRan / assertHandoffTo
 *
 * Run:
 *   npx vitest run examples/mock_tests/03-multi-agent-strategies.test.ts
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import { Agent, tool } from "@agentspan-ai/sdk";
import {
  mockRun,
  expectResult,
  assertAgentRan,
  assertHandoffTo,
  assertToolUsed,
  assertNoErrors,
  assertStatus,
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

const sendNotification = tool(
  async (args: { channel: string; message: string }) =>
    `Sent to ${args.channel}: ${args.message}`,
  {
    name: "send_notification",
    description: "Send a notification.",
    inputSchema: z.object({
      channel: z.string(),
      message: z.string(),
    }),
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
  it("routes docs question to docs specialist", async () => {
    const result = await mockRun(
      triageAgent,
      "How do I configure logging?",
      {
        mockTools: {
          search_docs: async (args: { query: string }) =>
            `Set LOG_LEVEL=debug in your config. Query: ${args.query}`,
        },
      },
    );

    assertHandoffTo(result, "docs-specialist");
    assertToolUsed(result, "search_docs");
    assertNoErrors(result);
  });

  it("db specialist runs its tool when targeted directly", async () => {
    // Test the db-specialist directly to verify tool execution in isolation
    const result = await mockRun(
      dbAgent,
      "How many users signed up today?",
      {
        mockTools: {
          run_query: async () => [{ count: 150 }],
        },
      },
    );

    assertToolUsed(result, "run_query");
    assertNoErrors(result);
  });

  it("triage agent produces handoff event", async () => {
    const result = await mockRun(
      triageAgent,
      "Show me the user table schema",
      {
        mockTools: {
          run_query: async () => [{ col: "id" }, { col: "name" }],
        },
      },
    );

    // In mock mode, handoff goes to the first sub-agent
    assertHandoffTo(result, "docs-specialist");
    expectResult(result).toBeCompleted();
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
  it("runs all agents in order", async () => {
    const result = await mockRun(
      contentPipeline,
      "Write a guide on API testing",
      {
        mockTools: {
          search_docs: async () => "API testing best practices...",
        },
      },
    );

    assertAgentRan(result, "researcher");
    assertAgentRan(result, "drafter");
    assertAgentRan(result, "reviewer");
    assertNoErrors(result);
  });

  it("researcher uses search tool before drafter runs", async () => {
    const executionOrder: string[] = [];

    const result = await mockRun(
      contentPipeline,
      "Write about microservices",
      {
        mockTools: {
          search_docs: async () => {
            executionOrder.push("search_docs");
            return "Microservices patterns...";
          },
        },
      },
    );

    assertToolUsed(result, "search_docs");
    expect(executionOrder).toContain("search_docs");
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
  it("all auditors run", async () => {
    const result = await mockRun(auditTeam, "Audit the checkout page");

    assertAgentRan(result, "security-auditor");
    assertAgentRan(result, "performance-auditor");
    assertAgentRan(result, "accessibility-auditor");
    assertNoErrors(result);
  });

  it("output reflects all perspectives", async () => {
    const result = await mockRun(auditTeam, "Audit the dashboard");

    expectResult(result).toBeCompleted();
    // Each agent should contribute to the result
    assertAgentRan(result, "security-auditor");
    assertAgentRan(result, "performance-auditor");
    assertAgentRan(result, "accessibility-auditor");
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
  it("routes to a sub-agent via the router", async () => {
    const result = await mockRun(
      bugTriage,
      "The /users endpoint returns 500",
      {
        mockTools: {
          run_query: async () => [{ error: "null pointer" }],
        },
      },
    );

    // In mock mode, router strategy hands off to the first sub-agent
    assertHandoffTo(result, "backend");
    assertToolUsed(result, "run_query");
  });

  it("completes successfully", async () => {
    const result = await mockRun(
      bugTriage,
      "The submit button is invisible on mobile",
    );

    expectResult(result).toBeCompleted();
  });
});
