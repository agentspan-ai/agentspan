/**
 * Suite 7: Media Tools — image and audio generation.
 *
 * Tests media generation tools end-to-end:
 *   - Image via OpenAI (dall-e-3) and Gemini (imagen-3.0)
 *   - Audio via OpenAI (tts-1)
 *
 * Skips if API keys not set. Media API errors skip (not test bugs).
 * No mocks. Real server, real LLM, real media APIs.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { Agent, AgentRuntime, imageTool, audioTool } from "@agentspan-ai/sdk";
import { checkServerHealth, MODEL, TIMEOUT, getWorkflow, runDiagnostic } from "./helpers";

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error("Server not available");
  runtime = new AgentRuntime();
});

afterAll(() => runtime.shutdown());

// ── Helpers ─────────────────────────────────────────────────────────────

function getAgentDef(plan: Record<string, unknown>): Record<string, unknown> {
  const wf = plan.workflowDef as Record<string, unknown>;
  const meta = wf.metadata as Record<string, unknown>;
  return meta.agentDef as Record<string, unknown>;
}

async function findMediaTask(executionId: string, taskTypePrefix: string) {
  const wf = await getWorkflow(executionId);
  const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
  return tasks.find(
    (t) =>
      String(t.taskType ?? "").includes(taskTypePrefix) ||
      String(t.taskDefName ?? "").includes(taskTypePrefix),
  );
}

async function assertMediaGenerated(
  result: { executionId: string; status: string; output?: unknown },
  stepName: string,
  taskTypePrefix: string,
) {
  const diag = runDiagnostic(result as unknown as Record<string, unknown>);
  expect(result.executionId).toBeTruthy();
  expect(result.status, `[${stepName}] ${diag}`).toBe("COMPLETED");

  const task = await findMediaTask(result.executionId, taskTypePrefix);
  expect(task, `[${stepName}] No ${taskTypePrefix} task in workflow`).toBeDefined();

  const taskStatus = String(task!.status ?? "");

  expect(taskStatus, `[${stepName}] ${taskTypePrefix} task status`).toBe("COMPLETED");
  expect(task!.outputData, `[${stepName}] empty outputData`).toBeDefined();
}

function assertToolCompiled(
  plan: Record<string, unknown>,
  expectedToolType: string,
  expectedModel: string,
  stepName: string,
) {
  const ad = getAgentDef(plan);
  const tools = (ad.tools ?? []) as Record<string, unknown>[];
  const matching = tools.filter((t) => t.toolType === expectedToolType);
  expect(matching.length, `[${stepName}] No ${expectedToolType} tool`).toBeGreaterThanOrEqual(1);
  const config = matching[0].config as Record<string, unknown> | undefined;
  const model = config?.model ?? matching[0].model;
  expect(model, `[${stepName}] wrong model`).toBe(expectedModel);
}

// ── Tests ───────────────────────────────────────────────────────────────

describe("Suite 7: Media Tools", { timeout: 600_000 }, () => {
  it.skipIf(!process.env.OPENAI_API_KEY)("image — OpenAI DALL-E 3", async () => {
    const img = imageTool({
      name: "gen_image",
      description: "Generate an image from text.",
      llmProvider: "openai",
      model: "dall-e-3",
    });
    const agent = new Agent({
      name: "e2e_ts_image_openai",
      model: MODEL,
      instructions: "Generate images when asked. Call gen_image.",
      tools: [img],
    });

    assertToolCompiled(
      (await runtime.plan(agent)) as Record<string, unknown>,
      "generate_image",
      "dall-e-3",
      "Image/OpenAI",
    );

    const result = await runtime.run(
      agent,
      'Generate an image of a red circle on a white background. Use size "1024x1024".',
      { timeout: TIMEOUT },
    );
    await assertMediaGenerated(result, "Image/OpenAI", "GENERATE_IMAGE");
  });

  it.skipIf(!process.env.GOOGLE_AI_API_KEY)("image — Gemini Imagen 3", async () => {
    const img = imageTool({
      name: "gen_image_gemini",
      description: "Generate image via Gemini.",
      llmProvider: "google_gemini",
      model: "imagen-3.0-generate-002",
    });
    const agent = new Agent({
      name: "e2e_ts_image_gemini",
      model: MODEL,
      instructions: "Generate images when asked. Call gen_image_gemini.",
      tools: [img],
    });

    assertToolCompiled(
      (await runtime.plan(agent)) as Record<string, unknown>,
      "generate_image",
      "imagen-3.0-generate-002",
      "Image/Gemini",
    );

    const result = await runtime.run(
      agent,
      "Generate an image of a blue square on a white background.",
      { timeout: TIMEOUT },
    );
    await assertMediaGenerated(result, "Image/Gemini", "GENERATE_IMAGE");
  });

  it.skipIf(!process.env.OPENAI_API_KEY)("audio — OpenAI TTS-1", async () => {
    const aud = audioTool({
      name: "gen_audio",
      description: "Convert text to speech.",
      llmProvider: "openai",
      model: "tts-1",
    });
    const agent = new Agent({
      name: "e2e_ts_audio_openai",
      model: MODEL,
      instructions: "Convert text to speech when asked. Call gen_audio.",
      tools: [aud],
    });

    assertToolCompiled(
      (await runtime.plan(agent)) as Record<string, unknown>,
      "generate_audio",
      "tts-1",
      "Audio/OpenAI",
    );

    const result = await runtime.run(
      agent,
      'Convert this to speech: "Hello, this is an end to end test."',
      { timeout: TIMEOUT },
    );
    await assertMediaGenerated(result, "Audio/OpenAI", "GENERATE_AUDIO");
  });
});
