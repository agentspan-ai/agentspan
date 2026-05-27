// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

/**
 * 108 — Plan-Execute with cross-step output piping via `Ref`.
 *
 * The `new Ref("step_id")` helper wires the **whole output** of an
 * upstream step into a downstream step's args. No JSON path, no field
 * selection, no internal task-ref naming to memorise — one expression
 * and the runtime substitutes the value at execution time.
 *
 * The example runs a three-step pipeline:
 *
 *     produce → enrich → report
 *
 * `produce` emits a record dict, `enrich` adds a derived field via
 * `Ref("produce")`, and `report` reads `Ref("enrich")` to format a
 * final summary. The plan is fully deterministic — no planner LLM
 * required — because we pass `plan` directly to `runtime.run`.
 *
 * Requirements:
 *   - Agentspan server running on http://localhost:6767 (or
 *     AGENTSPAN_SERVER_URL)
 *   - AGENTSPAN_LLM_MODEL set (default: openai/gpt-4o-mini)
 *
 * Run: npx tsx examples/108-plan-execute-refs.ts
 */

import {
  Agent,
  AgentRuntime,
  Op,
  Plan,
  Ref,
  Step,
  tool,
} from "../src/index.js";

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? "openai/gpt-4o-mini";

const produce = tool(
  async ({ record_id }: { record_id: string }) => ({
    record_id,
    value: 42,
    tags: ["alpha", "beta"],
  }),
  {
    name: "produce",
    description: "Return a fixed payload.",
    inputSchema: {
      type: "object",
      properties: { record_id: { type: "string" } },
      required: ["record_id"],
    },
  },
);

const enrich = tool(
  async ({ record }: { record: Record<string, unknown> }) => ({
    ...record,
    value_squared: ((record.value as number) ?? 0) ** 2,
  }),
  {
    name: "enrich",
    description: "Append a derived field. Reads the whole `produce` output via Ref.",
    inputSchema: {
      type: "object",
      properties: { record: { type: "object" } },
      required: ["record"],
    },
  },
);

const report = tool(
  async ({
    record,
    enriched,
  }: {
    record: { record_id: string; value: number; tags: string[] };
    enriched: { value_squared: number };
  }) => ({
    id: record.record_id,
    original_value: record.value,
    squared: enriched.value_squared,
    tags_joined: record.tags.join(", "),
    summary: `record=${record.record_id} value=${record.value} squared=${enriched.value_squared} tags=${JSON.stringify(record.tags)}`,
  }),
  {
    name: "report",
    description: "Format the final report. Reads BOTH upstream steps via Refs.",
    inputSchema: {
      type: "object",
      properties: {
        record: { type: "object" },
        enriched: { type: "object" },
      },
      required: ["record", "enriched"],
    },
  },
);

async function main() {
  const planner = new Agent({
    name: "ref_demo_planner",
    model: MODEL,
    instructions: "(planner unused; static plan supplied)",
  });

  const harness = new Agent({
    name: "ref_demo",
    model: MODEL,
    strategy: "plan_execute",
    planner,
    tools: [produce, enrich, report],
  });

  // Typed plan — no JSON strings, no field selectors. Each Ref serialises
  // to {"$ref": "<step_id>"} which the server rewrites to the right
  // Conductor template at compile time.
  const plan = new Plan({
    steps: [
      new Step("produce", {
        operations: [new Op("produce", { args: { record_id: "r-001" } })],
      }),
      new Step("enrich", {
        dependsOn: ["produce"],
        operations: [new Op("enrich", { args: { record: new Ref("produce") } })],
      }),
      new Step("report", {
        dependsOn: ["produce", "enrich"],
        operations: [
          new Op("report", {
            args: {
              record: new Ref("produce"),
              enriched: new Ref("enrich"),
            },
          }),
        ],
      }),
    ],
  });

  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(harness, "demo", { plan, timeoutSeconds: 120 });
    console.log(`status=${result.status} executionId=${result.executionId}`);
    await showPipelineOutputs(result.executionId);
  } finally {
    await runtime.shutdown();
  }
}

async function showPipelineOutputs(executionId: string) {
  const base = (process.env.AGENTSPAN_SERVER_URL ?? "http://localhost:6767/api")
    .replace(/\/api$/, "")
    .replace(/\/$/, "");
  const parent = (await (await fetch(`${base}/api/workflow/${executionId}?includeTasks=true`)).json()) as {
    tasks?: Array<{ referenceTaskName?: string; outputData?: { subWorkflowId?: string } }>;
  };
  let subId: string | undefined;
  for (const t of parent.tasks ?? []) {
    if (t.referenceTaskName?.endsWith("_plan_exec")) {
      subId = t.outputData?.subWorkflowId;
      break;
    }
  }
  if (!subId) return;
  const sub = (await (await fetch(`${base}/api/workflow/${subId}?includeTasks=true`)).json()) as {
    tasks?: Array<{ taskDefName?: string; outputData?: unknown }>;
  };
  console.log("\n── pipeline trace (Ref data flow) ────────────────────────");
  for (const t of sub.tasks ?? []) {
    if (["produce", "enrich", "report"].includes(t.taskDefName ?? "")) {
      console.log(`\n${t.taskDefName}:`);
      console.log(JSON.stringify(t.outputData, null, 2));
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
