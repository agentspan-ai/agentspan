// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.ToolContext;
import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.*;

/**
 * Suite 2 — runtime credential lifecycle (standalone, no secret backend).
 *
 * <p>Secrets are delegated to the Orkes host via {@code ${workflow.secrets.NAME}}.
 * Standalone/CI has NO secret backend and NO way to inject a secret value into a
 * running tool, so the legacy "set a secret via /api/secrets and assert the tool
 * received it" steps are no longer applicable. We keep the credential-independent
 * guarantees:
 * <ol>
 *   <li>A tool that needs NO credential runs and its task is COMPLETED.</li>
 *   <li>A tool REQUIRING a credential, with no secret backend, does NOT succeed —
 *       its task is in a non-COMPLETED failure state and the tool body never
 *       produced its success output (env is not a silent fallback).</li>
 * </ol>
 *
 * <p>Java is tier-1-only — the SDK reads secrets only from the server, never from
 * {@code System.getenv}, so the "env vars not used as fallback" security check is
 * structurally satisfied by language design and asserted explicitly below.</p>
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class Suite2ToolCallingCredentials extends BaseTest {

    private static final String CRED_A = "E2E_JAVA_CRED_A";

    private static AgentRuntime runtime;

    // ── Tool that needs NO credential ────────────────────────────────────────

    public static class FreeTools {
        @Tool(name = "free_tool", description = "Tool that needs no credential. Echoes its input.")
        public Map<String, Object> freeTool(String x) {
            return Map.of("echo", "free:" + x);
        }
    }

    // ── Tool that reads CRED_A via the Secrets accessor ──────────────────────

    public static class PaidGithubTools {
        @Tool(
                name = "paid_tool_a",
                description = "Tool that needs E2E_JAVA_CRED_A. Returns first 3 chars of the credential.",
                credentials = {"E2E_JAVA_CRED_A"})
        public Map<String, Object> paidToolA(String x, ToolContext ctx) {
            String value = ctx.getCredentialOrNull(CRED_A);
            if (value == null) {
                throw new IllegalStateException("Credential " + CRED_A + " not in Secrets context. "
                        + "WorkerManager should have failed the task terminally before reaching here.");
            }
            return Map.of("preview", "paid_a:" + value.substring(0, Math.min(3, value.length())));
        }
    }

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new AgentConfig(100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Test: tool needing no credential runs and COMPLETES ──────────────────

    @Test
    @Order(1)
    void step1_noCredentialNeeded_taskCompletes() {
        Agent agent = buildFreeAgent();
        AgentResult result =
                runtime.run(agent, "Call free_tool exactly once with the argument 'test' and report what it returns.");

        assertNotNull(result.getExecutionId(), "result must include an execution id");

        Map<String, Object> wf = getWorkflow(result.getExecutionId());
        Map<String, Object> freeTask = findToolTask(wf, "free_tool");
        assertNotNull(freeTask, "free_tool task not found in workflow — run shape changed?");
        assertEquals(
                "COMPLETED",
                freeTask.get("status"),
                "Step 1 expected free_tool COMPLETED, got '" + freeTask.get("status") + "'.\n" + "  task=" + freeTask);
    }

    // ── Test: tool requiring a credential, no backend → does NOT succeed ──────

    @Test
    @Order(2)
    void step2_credentialRequiredButNoBackend_taskDoesNotSucceed() {
        // No secret backend exists in standalone, and the SDK reads secrets only
        // from the server, never from System.getenv. So the paid tool must NOT
        // succeed, and its body must NOT produce its success output ("paid_a:").
        Agent agent = buildPaidAgent();
        AgentResult result =
                runtime.run(agent, "Call paid_tool_a exactly once with 'test' and report what it returns.");

        Map<String, Object> wf = getWorkflow(result.getExecutionId());
        Map<String, Object> paidTask = findToolTask(wf, "paid_tool_a");
        assertNotNull(paidTask, "paid_tool_a task not found in workflow — run shape changed?");

        Set<String> failure = Set.of("FAILED", "FAILED_WITH_TERMINAL_ERROR", "COMPLETED_WITH_ERRORS", "TERMINATED");
        String status = (String) paidTask.get("status");
        assertTrue(
                failure.contains(status),
                "Step 2 expected paid_tool_a status in " + failure + ", got '" + status
                        + "'. Missing credential with no backend must not succeed.\n"
                        + "  task=" + paidTask);

        // Env is not a silent fallback: the tool body must not have produced its
        // success output.
        String output = String.valueOf(paidTask.get("outputData"));
        assertFalse(output.contains("paid_a:"), "tool body should not have produced its success output");
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private Agent buildFreeAgent() {
        List<ToolDef> tools = ToolRegistry.fromInstance(new FreeTools());
        return Agent.builder()
                .name("e2e_java_free_tool")
                .model(MODEL)
                .instructions("You have one tool: free_tool. You MUST call it exactly once "
                        + "with the argument 'test'. Then report its output verbatim.")
                .tools(tools)
                .maxTurns(3)
                .build();
    }

    private Agent buildPaidAgent() {
        List<ToolDef> tools = ToolRegistry.fromInstance(new PaidGithubTools());
        return Agent.builder()
                .name("e2e_java_cred_lifecycle")
                .model(MODEL)
                .instructions("You have one tool: paid_tool_a. You MUST call it exactly once "
                        + "with the argument 'test'. Then report its output verbatim.")
                .tools(tools)
                .maxTurns(3)
                .build();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> findToolTask(Map<String, Object> wf, String name) {
        List<Map<String, Object>> tasks = (List<Map<String, Object>>) wf.getOrDefault("tasks", List.of());
        for (Map<String, Object> t : tasks) {
            String ref = String.valueOf(t.getOrDefault("referenceTaskName", ""));
            String def = String.valueOf(t.getOrDefault("taskDefName", ""));
            String typ = String.valueOf(t.getOrDefault("taskType", ""));
            if (ref.contains(name) || def.equals(name) || typ.equals(name)) {
                return t;
            }
        }
        return null;
    }
}
