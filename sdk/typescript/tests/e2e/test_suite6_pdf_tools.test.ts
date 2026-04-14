/**
 * Suite 6: PDF Tools — markdown-to-PDF generation.
 *
 * Tests PDF tool integration:
 *   1. Agent compiles with generate_pdf tool type
 *   2. Agent generates PDF from markdown
 *   3. GENERATE_PDF task completes in workflow
 *
 * No mocks. Real server, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { Agent, AgentRuntime, pdfTool } from "@agentspan-ai/sdk";
import { checkServerHealth, MODEL, TIMEOUT, getWorkflow, runDiagnostic } from "./helpers";

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error("Server not available");
  runtime = new AgentRuntime();
});

afterAll(() => runtime.shutdown());

// ── Sample markdown ─────────────────────────────────────────────────────

const SAMPLE_MARKDOWN = `# Agentspan E2E Test Report

## Overview

This document validates the PDF generation pipeline.

## Key Metrics

| Metric       | Value |
|-------------|-------|
| Tests Run   | 12    |
| Passed      | 11    |
| Skipped     | 1     |

## Features Tested

- MCP tool discovery and execution
- HTTP tool with OpenAPI spec
- Credential lifecycle management

## Conclusion

All critical paths validated successfully.
`;

// ── Helpers ─────────────────────────────────────────────────────────────

function getAgentDef(plan: Record<string, unknown>): Record<string, unknown> {
  const wf = plan.workflowDef as Record<string, unknown>;
  const meta = wf.metadata as Record<string, unknown>;
  return meta.agentDef as Record<string, unknown>;
}

async function findPdfTask(executionId: string) {
  const wf = await getWorkflow(executionId);
  const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
  return tasks.find(
    (t) =>
      String(t.taskType ?? "").includes("GENERATE_PDF") ||
      String(t.taskDefName ?? "").includes("GENERATE_PDF") ||
      String(t.taskType ?? "")
        .toLowerCase()
        .includes("pdf"),
  );
}

// ── Tests ───────────────────────────────────────────────────────────────

describe("Suite 6: PDF Tools", { timeout: 300_000 }, () => {
  it("PDF generation and plan validation", async () => {
    const pdf = pdfTool({ name: "generate_pdf", description: "Generate a PDF from markdown." });
    const agent = new Agent({
      name: "e2e_ts_pdf_gen",
      model: MODEL,
      instructions:
        "You generate PDF documents from markdown. Call generate_pdf with the exact markdown provided.",
      tools: [pdf],
    });

    // ── Step 0: Verify compilation ──────────────────────────────
    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);
    const tools = (ad.tools ?? []) as Record<string, unknown>[];
    const pdfTools = tools.filter((t) => t.toolType === "generate_pdf");
    expect(pdfTools.length, "Expected 1 generate_pdf tool").toBe(1);

    // ── Step 1: Generate PDF ────────────────────────────────────
    const result = await runtime.run(
      agent,
      `Convert this markdown to PDF. Pass it exactly as-is:\n\n${SAMPLE_MARKDOWN}`,
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(result.status, `[PDF Gen] ${diag}`).toBe("COMPLETED");

    // ── Step 2: Verify GENERATE_PDF task ────────────────────────
    const pdfTask = await findPdfTask(result.executionId);
    expect(pdfTask, "[PDF Gen] No GENERATE_PDF task in workflow").toBeDefined();
    expect(pdfTask!.status, "[PDF Gen] GENERATE_PDF task status").toBe("COMPLETED");

    const outputData = pdfTask!.outputData as Record<string, unknown> | undefined;
    expect(outputData, "[PDF Gen] Empty outputData").toBeDefined();
  });
});
