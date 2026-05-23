// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// 115 — Plan-Execute with `PlannerContext`: customer onboarding plan.
//
// The PAE planner's static `Instructions` string is fine for *how* to emit
// a plan, but it's a poor fit for the domain-specific rules a real plan
// depends on — tier thresholds, KYC step ordering, region exceptions,
// escalation rules. Those live in docs that change weekly, not in code.
//
// `PlannerContext` solves this: a list of text snippets and/or URLs
// appended to the planner's user prompt as a `## Reference Context` block
// on every planner invocation. URLs are fetched dynamically — no compile-
// time fetch, no cache — so a Confluence edit lands on the next plan run
// with zero redeploy.
//
// This example runs WITHOUT a real Confluence backend — the
// `PlannerContext` is text-only by default. The `Context.FromUrl(...)`
// example below is commented as a reference for how real installations
// wire credentialed docs.
//
// Mirrors sdk/python/examples/115_plan_execute_planner_context.py,
// sdk/typescript/examples/115-plan-execute-planner-context.ts,
// and sdk/java/examples/.../Example115PlannerContext.java.

using Agentspan;
using Agentspan.Examples;
using Agentspan.Plans;

// ── Onboarding tools (deterministic, no external calls) ──────────────

internal sealed class OnboardingTools
{
    [Tool("Validate a single KYC document. Phase 1 of onboarding.")]
    public Dictionary<string, object> ValidateKyc(string customer_id, string doc_type) => new()
    {
        ["customer_id"] = customer_id,
        ["doc_type"] = doc_type,
        ["status"] = "verified",
    };

    [Tool("Provision the customer's account record. Phase 2 of onboarding.")]
    public Dictionary<string, object> CreateAccount(string customer_id, string tier) => new()
    {
        ["customer_id"] = customer_id,
        ["tier"] = tier,
        ["account_id"] = $"acct_{customer_id}_{tier}",
        ["status"] = "active",
    };

    [Tool("Send the tier-appropriate welcome email. Phase 3 of onboarding.")]
    public Dictionary<string, object> SendWelcomeEmail(string customer_id, string account_id) => new()
    {
        ["customer_id"] = customer_id,
        ["account_id"] = account_id,
        ["message_id"] = $"msg_{customer_id}",
        ["status"] = "sent",
    };

    [Tool("Schedule the enterprise-tier kickoff call. Conditional on tier.")]
    public Dictionary<string, object> ScheduleKickoffCall(string customer_id, string account_id) => new()
    {
        ["customer_id"] = customer_id,
        ["account_id"] = account_id,
        ["calendar_invite_id"] = $"cal_{customer_id}",
        ["status"] = "scheduled",
    };
}

// ── Agents ──────────────────────────────────────────────────────────

var planner = new Agent("onboarding_planner")
{
    Model = Settings.LlmModel,
    MaxTurns = 3,
    Instructions =
        "You are an onboarding plan generator. Output a JSON plan that "
        + "validates KYC, creates the account, and notifies the customer. "
        + "Follow the rules in the Reference Context block exactly.",
};

var fallback = new Agent("onboarding_fallback")
{
    Model = Settings.LlmModel,
    MaxTurns = 3,
    Instructions =
        "If you receive this, the plan compile failed. Run the four "
        + "onboarding tools in their natural order: validate_kyc, "
        + "create_account, send_welcome_email, and schedule_kickoff_call "
        + "if the customer tier is 'enterprise'.",
    Tools = ToolRegistry.FromInstance(new OnboardingTools()),
};

var harness = new Agent("onboarding_harness")
{
    Model = Settings.LlmModel,
    Strategy = Strategy.PlanExecute,
    Planner = planner,
    Fallback = fallback,
    FallbackMaxTurns = 3,
    Tools = ToolRegistry.FromInstance(new OnboardingTools()),
    PlannerContext = new List<Context>
    {
        // ── Inline rules: short, stable, hand-edited in code ──
        Context.FromText(
            "Onboarding has 3 mandatory phases in this exact order: "
            + "(1) validate_kyc with doc_type='id', "
            + "(2) create_account, "
            + "(3) send_welcome_email."),
        Context.FromText(
            "Tier 'enterprise' customers ADDITIONALLY require step "
            + "(4) schedule_kickoff_call AFTER send_welcome_email. "
            + "Tiers 'starter' and 'pro' must NOT include this step."),
        Context.FromText(
            "send_welcome_email depends on create_account's output: "
            + "use the account_id field as the account_id arg."),

        // ── Live doc (commented out — uncomment if you have a real
        //     compliance/Confluence URL + token, demonstrates the
        //     URL+auth path the same way ToolConfig.Headers does):
        // Context.FromUrl(
        //     "https://docs.example.com/onboarding-compliance.md",
        //     headers: new Dictionary<string, string>
        //     {
        //         ["Authorization"] = "Bearer ${CONFLUENCE_TOKEN}",
        //     },
        //     required: true,  // workflow fails if the doc can't be fetched
        //     maxBytes: 8192), // truncate giant wikis at 8KB
    },
};

const string prompt =
    "Onboard customer cust-001 at tier 'enterprise'. "
    + "Use customer_id='cust-001' and tier='enterprise' for the tools.";

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(harness, prompt);

Console.WriteLine($"status: {result.Status}");
Console.WriteLine($"output: {result.Output}");

// Surface the executed plan steps so this example doubles as a proof
// that the planner actually used the context (4 steps when
// tier=enterprise, 3 when tier=starter/pro).
await ShowExecutedSteps(result.ExecutionId);

static async Task ShowExecutedSteps(string executionId)
{
    var baseUrl = (Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL")
        ?? "http://localhost:6767/api")
        .TrimEnd('/')
        .Replace("/api", "");
    using var http = new HttpClient();
    var parent = await http.GetFromJsonAsync<System.Text.Json.JsonElement>(
        $"{baseUrl}/api/workflow/{executionId}?includeTasks=true");

    Console.WriteLine("\n=== Executed onboarding plan ===");

    string? subId = null;
    if (parent.TryGetProperty("tasks", out var tasks))
    {
        foreach (var t in tasks.EnumerateArray())
        {
            var refName = t.TryGetProperty("referenceTaskName", out var rn)
                ? rn.GetString() ?? string.Empty
                : string.Empty;
            if (refName.EndsWith("_plan_exec"))
            {
                if (t.TryGetProperty("outputData", out var od)
                    && od.TryGetProperty("subWorkflowId", out var sid))
                {
                    subId = sid.GetString();
                }
                break;
            }
        }
    }

    if (subId == null)
    {
        Console.WriteLine("  (no plan_exec sub-workflow — planner output was rejected)");
        return;
    }

    var sub = await http.GetFromJsonAsync<System.Text.Json.JsonElement>(
        $"{baseUrl}/api/workflow/{subId}?includeTasks=true");
    var expected = new HashSet<string>
    {
        "validate_kyc", "create_account", "send_welcome_email", "schedule_kickoff_call",
    };
    int count = 0;
    bool sawKickoff = false;
    if (sub.TryGetProperty("tasks", out var subTasks))
    {
        foreach (var t in subTasks.EnumerateArray())
        {
            var name = t.TryGetProperty("taskDefName", out var n) ? n.GetString() ?? "" : "";
            if (expected.Contains(name))
            {
                count++;
                if (name == "schedule_kickoff_call") sawKickoff = true;
                var status = t.TryGetProperty("status", out var s) ? s.GetString() : "";
                Console.WriteLine($"    {status,-10} {name}");
            }
        }
    }
    Console.WriteLine($"  {count} step(s) executed");
    if (sawKickoff)
    {
        Console.WriteLine("  ✓ planner picked up the 'enterprise tier needs kickoff' rule");
    }
}
