// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

/**
 * 115 — Plan-Execute with `plannerContext`: customer onboarding plan.
 *
 * The PAE planner's static `instructions` string is fine for *how* to
 * emit a plan, but it's a poor fit for the domain-specific rules a
 * real plan depends on — tier thresholds, KYC step ordering, region
 * exceptions, escalation rules. Those live in docs that change weekly,
 * not in code.
 *
 * `plannerContext` solves this: a list of text snippets and/or URLs
 * appended to the planner's user prompt as a `## Reference Context`
 * block on every planner invocation. URLs are fetched dynamically —
 * no compile-time fetch, no cache — so a Confluence edit lands on the
 * next plan run with zero redeploy.
 *
 * This example runs WITHOUT a real Confluence backend — the
 * `plannerContext` is text-only by default so you can run it against
 * a stock server without setting up credentials. The `new Context({url: ...})`
 * example below is commented as a reference for how real installations
 * wire credentialed docs.
 *
 * Mirrors sdk/python/examples/115_plan_execute_planner_context.py.
 *
 * Requirements:
 *   - Agentspan server running on http://localhost:6767 (or
 *     AGENTSPAN_SERVER_URL)
 *   - AGENTSPAN_LLM_MODEL set (default: openai/gpt-4o-mini)
 *
 * Run: npx tsx examples/115-plan-execute-planner-context.ts
 */

import {
  Agent,
  AgentRuntime,
  Context,
  tool,
} from "../src/index.js";

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? "openai/gpt-4o-mini";

// ── Onboarding tools (deterministic, no external calls) ──────────────

const validateKyc = tool(
  async ({ customer_id, doc_type }: { customer_id: string; doc_type: string }) => ({
    customer_id,
    doc_type,
    status: "verified",
  }),
  {
    name: "validate_kyc",
    description: "Validate a single KYC document. Phase 1 of onboarding.",
    inputSchema: {
      type: "object",
      properties: {
        customer_id: { type: "string" },
        doc_type: { type: "string" },
      },
      required: ["customer_id", "doc_type"],
    },
  },
);

const createAccount = tool(
  async ({ customer_id, tier }: { customer_id: string; tier: string }) => ({
    customer_id,
    tier,
    account_id: `acct_${customer_id}_${tier}`,
    status: "active",
  }),
  {
    name: "create_account",
    description: "Provision the customer's account record. Phase 2 of onboarding.",
    inputSchema: {
      type: "object",
      properties: {
        customer_id: { type: "string" },
        tier: { type: "string" },
      },
      required: ["customer_id", "tier"],
    },
  },
);

const sendWelcomeEmail = tool(
  async ({
    customer_id,
    account_id,
  }: {
    customer_id: string;
    account_id: string;
  }) => ({
    customer_id,
    account_id,
    message_id: `msg_${customer_id}`,
    status: "sent",
  }),
  {
    name: "send_welcome_email",
    description: "Send the tier-appropriate welcome email. Phase 3 of onboarding.",
    inputSchema: {
      type: "object",
      properties: {
        customer_id: { type: "string" },
        account_id: { type: "string" },
      },
      required: ["customer_id", "account_id"],
    },
  },
);

const scheduleKickoffCall = tool(
  async ({
    customer_id,
    account_id,
  }: {
    customer_id: string;
    account_id: string;
  }) => ({
    customer_id,
    account_id,
    calendar_invite_id: `cal_${customer_id}`,
    status: "scheduled",
  }),
  {
    name: "schedule_kickoff_call",
    description: "Schedule the enterprise-tier kickoff call. Conditional on tier.",
    inputSchema: {
      type: "object",
      properties: {
        customer_id: { type: "string" },
        account_id: { type: "string" },
      },
      required: ["customer_id", "account_id"],
    },
  },
);

async function main(): Promise<void> {
  const planner = new Agent({
    name: "onboarding_planner",
    model: MODEL,
    maxTurns: 3,
    instructions:
      "You are an onboarding plan generator. Output a JSON plan that " +
      "validates KYC, creates the account, and notifies the customer. " +
      "Follow the rules in the Reference Context block exactly.",
  });

  const fallback = new Agent({
    name: "onboarding_fallback",
    model: MODEL,
    maxTurns: 3,
    instructions:
      "If you receive this, the plan compile failed. Run the four " +
      "onboarding tools in their natural order: validate_kyc, " +
      "create_account, send_welcome_email, and schedule_kickoff_call " +
      "if the customer tier is 'enterprise'.",
    tools: [validateKyc, createAccount, sendWelcomeEmail, scheduleKickoffCall],
  });

  const harness = new Agent({
    name: "onboarding_harness",
    model: MODEL,
    tools: [validateKyc, createAccount, sendWelcomeEmail, scheduleKickoffCall],
    planner,
    fallback,
    strategy: "plan_execute",
    fallbackMaxTurns: 3,
    plannerContext: [
      // Inline rules — short, stable, hand-edited in code.
      // Bare strings auto-wrap to Context({text: ...}). Explicit
      // Context({text: ...}) is shown on the third entry to make
      // both shapes visible in one example.
      "Onboarding has 3 mandatory phases in this exact order: " +
        "(1) validate_kyc with doc_type='id', " +
        "(2) create_account, " +
        "(3) send_welcome_email.",
      "Tier 'enterprise' customers ADDITIONALLY require step " +
        "(4) schedule_kickoff_call AFTER send_welcome_email. " +
        "Tiers 'starter' and 'pro' must NOT include this step.",
      new Context({
        text:
          "send_welcome_email depends on create_account's output: " +
          "use the account_id field as the account_id arg.",
      }),
      // Live doc (commented out — uncomment if you have a real
      // compliance/Confluence URL + token, demonstrates the URL+auth
      // path the same way ToolConfig.headers does):
      // new Context({
      //   url: "https://docs.example.com/onboarding-compliance.md",
      //   headers: { Authorization: "Bearer ${CONFLUENCE_TOKEN}" },
      //   required: true,   // workflow fails if the doc can't be fetched
      //   maxBytes: 8192,   // truncate giant wikis at 8KB
      // }),
    ],
  });

  const prompt =
    "Onboard customer cust-001 at tier 'enterprise'. " +
    "Use customer_id='cust-001' and tier='enterprise' for the tools.";

  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(harness, prompt, { timeout: 180 });
    console.log("status:", result.status);
    console.log("output:", JSON.stringify(result.output, null, 2));
    await showExecutedSteps(result.executionId);
  } finally {
    await runtime.close();
  }
}

async function showExecutedSteps(executionId: string): Promise<void> {
  const baseUrl = (
    process.env.AGENTSPAN_SERVER_URL ?? "http://localhost:6767/api"
  )
    .replace(/\/$/, "")
    .replace(/\/api$/, "");

  const parentResp = await fetch(
    `${baseUrl}/api/workflow/${executionId}?includeTasks=true`,
  );
  const parent = (await parentResp.json()) as {
    tasks?: Array<{
      referenceTaskName?: string;
      outputData?: { subWorkflowId?: string };
    }>;
  };

  console.log("\n=== Executed onboarding plan ===");

  const planExec = parent.tasks?.find((t) =>
    (t.referenceTaskName ?? "").endsWith("_plan_exec"),
  );
  const subId = planExec?.outputData?.subWorkflowId;
  if (!subId) {
    console.log("  (no plan_exec sub-workflow — planner output was rejected)");
    return;
  }

  const subResp = await fetch(
    `${baseUrl}/api/workflow/${subId}?includeTasks=true`,
  );
  const sub = (await subResp.json()) as {
    tasks?: Array<{ taskDefName?: string; status?: string }>;
  };

  const expected = new Set([
    "validate_kyc",
    "create_account",
    "send_welcome_email",
    "schedule_kickoff_call",
  ]);
  const toolTasks = (sub.tasks ?? []).filter((t) =>
    expected.has(t.taskDefName ?? ""),
  );

  if (toolTasks.length === 0) {
    console.log("  (no tool tasks executed)");
    return;
  }

  console.log(`  ${toolTasks.length} step(s) executed:`);
  for (const t of toolTasks) {
    console.log(`    ${(t.status ?? "").padEnd(10)} ${t.taskDefName}`);
  }
  if (toolTasks.some((t) => t.taskDefName === "schedule_kickoff_call")) {
    console.log("  ✓ planner picked up the 'enterprise tier needs kickoff' rule");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
