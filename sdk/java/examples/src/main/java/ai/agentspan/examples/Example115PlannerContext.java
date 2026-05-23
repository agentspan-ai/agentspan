// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.plans.Context;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 115 — Plan-Execute with {@code plannerContext}: customer onboarding plan.
 *
 * <p>The PAE planner's static {@code instructions} string is fine for
 * <em>how</em> to emit a plan, but it's a poor fit for the domain-specific
 * rules a real plan depends on — tier thresholds, KYC step ordering,
 * region exceptions, escalation rules. Those live in docs that change
 * weekly, not in code.
 *
 * <p>{@code plannerContext} solves this: a list of text snippets and/or
 * URLs appended to the planner's user prompt as a {@code ## Reference
 * Context} block on every planner invocation. URLs are fetched
 * dynamically — no compile-time fetch, no cache — so a Confluence edit
 * lands on the next plan run with zero redeploy.
 *
 * <p>This example runs WITHOUT a real Confluence backend — the
 * {@code plannerContext} is text-only by default so you can run it
 * against a stock server without setting up credentials. The
 * {@code Context.builder().url(...).header(...)} example below is
 * commented as a reference for how real installations wire credentialed
 * docs.
 *
 * <p>Mirrors sdk/python/examples/115_plan_execute_planner_context.py and
 * sdk/typescript/examples/115-plan-execute-planner-context.ts.
 *
 * <p>Run: {@code ./gradlew :examples:run -PmainClass=ai.agentspan.examples.Example115PlannerContext}
 */
public class Example115PlannerContext {

    private static final String MODEL =
        System.getenv().getOrDefault("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini");
    private static final String BASE_URL =
        System.getenv().getOrDefault("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
            .replace("/api", "");

    public static void main(String[] args) throws Exception {
        // ── Onboarding tools (deterministic, no external calls) ──────

        ToolDef validateKyc = ToolDef.builder()
            .name("validate_kyc")
            .description("Validate a single KYC document. Phase 1 of onboarding.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "customer_id", Map.of("type", "string"),
                    "doc_type", Map.of("type", "string")),
                "required", List.of("customer_id", "doc_type")))
            .toolType("worker")
            .func(input -> Map.of(
                "customer_id", input.get("customer_id"),
                "doc_type", input.get("doc_type"),
                "status", "verified"))
            .build();

        ToolDef createAccount = ToolDef.builder()
            .name("create_account")
            .description("Provision the customer's account record. Phase 2 of onboarding.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "customer_id", Map.of("type", "string"),
                    "tier", Map.of("type", "string")),
                "required", List.of("customer_id", "tier")))
            .toolType("worker")
            .func(input -> {
                Object cid = input.get("customer_id");
                Object tier = input.get("tier");
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("customer_id", cid);
                out.put("tier", tier);
                out.put("account_id", "acct_" + cid + "_" + tier);
                out.put("status", "active");
                return out;
            })
            .build();

        ToolDef sendWelcomeEmail = ToolDef.builder()
            .name("send_welcome_email")
            .description("Send the tier-appropriate welcome email. Phase 3 of onboarding.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "customer_id", Map.of("type", "string"),
                    "account_id", Map.of("type", "string")),
                "required", List.of("customer_id", "account_id")))
            .toolType("worker")
            .func(input -> {
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("customer_id", input.get("customer_id"));
                out.put("account_id", input.get("account_id"));
                out.put("message_id", "msg_" + input.get("customer_id"));
                out.put("status", "sent");
                return out;
            })
            .build();

        ToolDef scheduleKickoffCall = ToolDef.builder()
            .name("schedule_kickoff_call")
            .description("Schedule the enterprise-tier kickoff call. Conditional on tier.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "customer_id", Map.of("type", "string"),
                    "account_id", Map.of("type", "string")),
                "required", List.of("customer_id", "account_id")))
            .toolType("worker")
            .func(input -> {
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("customer_id", input.get("customer_id"));
                out.put("account_id", input.get("account_id"));
                out.put("calendar_invite_id", "cal_" + input.get("customer_id"));
                out.put("status", "scheduled");
                return out;
            })
            .build();

        // ── Agents ───────────────────────────────────────────────────

        Agent planner = Agent.builder()
            .name("onboarding_planner")
            .model(MODEL)
            .maxTurns(3)
            .instructions(
                "You are an onboarding plan generator. Output a JSON plan that "
                    + "validates KYC, creates the account, and notifies the customer. "
                    + "Follow the rules in the Reference Context block exactly.")
            .build();

        Agent fallback = Agent.builder()
            .name("onboarding_fallback")
            .model(MODEL)
            .maxTurns(3)
            .instructions(
                "If you receive this, the plan compile failed. Run the four "
                    + "onboarding tools in their natural order: validate_kyc, "
                    + "create_account, send_welcome_email, and schedule_kickoff_call "
                    + "if the customer tier is 'enterprise'.")
            .tools(List.of(validateKyc, createAccount, sendWelcomeEmail, scheduleKickoffCall))
            .build();

        Agent harness = Agent.builder()
            .name("onboarding_harness")
            .model(MODEL)
            .strategy(Strategy.PLAN_EXECUTE)
            .planner(planner)
            .fallback(fallback)
            .fallbackMaxTurns(3)
            .tools(List.of(validateKyc, createAccount, sendWelcomeEmail, scheduleKickoffCall))
            .plannerContext(List.of(
                // ── Inline rules: short, stable, hand-edited in code ──
                Context.text(
                    "Onboarding has 3 mandatory phases in this exact order: "
                        + "(1) validate_kyc with doc_type='id', "
                        + "(2) create_account, "
                        + "(3) send_welcome_email."),
                Context.text(
                    "Tier 'enterprise' customers ADDITIONALLY require step "
                        + "(4) schedule_kickoff_call AFTER send_welcome_email. "
                        + "Tiers 'starter' and 'pro' must NOT include this step."),
                Context.text(
                    "send_welcome_email depends on create_account's output: "
                        + "use the account_id field as the account_id arg.")
                // ── Live doc (commented out — uncomment if you have a real
                //     compliance/Confluence URL + token, demonstrates the
                //     URL+auth path the same way ToolConfig.headers does):
                // , Context.builder()
                //     .url("https://docs.example.com/onboarding-compliance.md")
                //     .header("Authorization", "Bearer ${CONFLUENCE_TOKEN}")
                //     .required(true)   // workflow fails if the doc can't be fetched
                //     .maxBytes(8192)   // truncate giant wikis at 8KB
                //     .build()
            ))
            .build();

        String prompt = "Onboard customer cust-001 at tier 'enterprise'. "
            + "Use customer_id='cust-001' and tier='enterprise' for the tools.";

        try (AgentRuntime runtime = new AgentRuntime()) {
            AgentResult result = runtime.run(harness, prompt);
            System.out.println("status: " + result.getStatus());
            System.out.println("output: " + result.getOutput());
            showExecutedSteps(result.getExecutionId());
        }
    }

    private static void showExecutedSteps(String executionId) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest parentReq = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/workflow/" + executionId + "?includeTasks=true"))
            .build();
        HttpResponse<String> parentResp =
            client.send(parentReq, HttpResponse.BodyHandlers.ofString());
        @SuppressWarnings("unchecked")
        Map<String, Object> parent = mapper.readValue(parentResp.body(), Map.class);

        System.out.println("\n=== Executed onboarding plan ===");

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> parentTasks =
            (List<Map<String, Object>>) parent.getOrDefault("tasks", List.of());
        String subId = null;
        for (Map<String, Object> t : parentTasks) {
            String ref = (String) t.getOrDefault("referenceTaskName", "");
            if (ref.endsWith("_plan_exec")) {
                @SuppressWarnings("unchecked")
                Map<String, Object> out = (Map<String, Object>) t.get("outputData");
                if (out != null) subId = (String) out.get("subWorkflowId");
                break;
            }
        }
        if (subId == null) {
            System.out.println("  (no plan_exec sub-workflow — planner output was rejected)");
            return;
        }

        HttpRequest subReq = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/workflow/" + subId + "?includeTasks=true"))
            .build();
        HttpResponse<String> subResp =
            client.send(subReq, HttpResponse.BodyHandlers.ofString());
        @SuppressWarnings("unchecked")
        Map<String, Object> sub = mapper.readValue(subResp.body(), Map.class);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> subTasks =
            (List<Map<String, Object>>) sub.getOrDefault("tasks", List.of());

        java.util.Set<String> expected = java.util.Set.of(
            "validate_kyc", "create_account", "send_welcome_email", "schedule_kickoff_call");
        int count = 0;
        boolean sawKickoff = false;
        for (Map<String, Object> t : subTasks) {
            String name = (String) t.getOrDefault("taskDefName", "");
            if (expected.contains(name)) {
                count++;
                if ("schedule_kickoff_call".equals(name)) sawKickoff = true;
                System.out.printf("    %-10s %s%n", t.get("status"), name);
            }
        }
        System.out.println("  " + count + " step(s) executed");
        if (sawKickoff) {
            System.out.println("  ✓ planner picked up the 'enterprise tier needs kickoff' rule");
        }
    }
}
