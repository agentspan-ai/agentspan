// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.Agentspan;
import ai.agentspan.examples.Settings;
import ai.agentspan.model.AgentHandle;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.DeploymentInfo;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.List;
import java.util.Map;

/**
 * Example Adk 37 — deploy + serve + run round-trip
 *
 * <p>Demonstrates the three Agentspan entry points working together with a
 * native ADK {@link LlmAgent} and zero bridge calls in user code:
 *
 * <ol>
 *   <li>{@link Agentspan#deploy(Object...)} — register the agent on the
 *       server. CI/CD step; idempotent; no workers polled.</li>
 *   <li>{@link Agentspan#serve(Object...)} — register local worker handlers
 *       and keep them polling. Long-running; normally a separate process.
 *       This example runs it on a daemon thread so a single JVM can play
 *       both client and worker roles.</li>
 *   <li>{@link Agentspan#start(Object, String)} — trigger an execution
 *       against the deployed agent and stream events back.</li>
 * </ol>
 *
 * <p>In production these three calls live in three different processes:
 *
 * <pre>{@code
 *   # one-shot CI/CD deploy
 *   $ java -cp ... DeployJob          // Agentspan.deploy(rootAgent)
 *
 *   # long-lived worker pool (Kubernetes Deployment, systemd unit, …)
 *   $ java -cp ... WorkerProcess      // Agentspan.serve(rootAgent)
 *
 *   # any caller, e.g. an HTTP handler
 *   $ curl -X POST .../api/agent/start -d '{"agentName":"deploy_demo_agent",...}'
 * }</pre>
 */
public class Example37DeployAndServe {

    @Schema(description = "Look up a fake user by ID.")
    public static Map<String, Object> lookupUser(
            @Schema(name = "user_id", description = "User ID") String userId) {
        Map<String, Map<String, Object>> directory = Map.of(
                "U001", Map.of("name", "Alice", "tier", "gold"),
                "U002", Map.of("name", "Bob",   "tier", "silver"));
        Map<String, Object> hit = directory.get(userId.toUpperCase());
        if (hit != null) {
            return Map.of("found", true, "user_id", userId, "name", hit.get("name"), "tier", hit.get("tier"));
        }
        return Map.of("found", false, "error", "User " + userId + " not found");
    }

    public static void main(String[] args) throws Exception {
        LlmAgent agent = LlmAgent.builder()
                .name("deploy_demo_agent")
                .description("Demo agent used by the deploy + serve + run example.")
                .model(Settings.LLM_MODEL)
                .instruction("""
                        You are a directory assistant. When asked about a user,
                        call the lookup_user tool with the user's ID and report
                        their name and tier.
                        """)
                .tools(FunctionTool.create(Example37DeployAndServe.class, "lookupUser"))
                .build();

        // ── Step 1: deploy ─────────────────────────────────────────────
        // Registers the workflow + task definitions on the server. Safe to
        // call repeatedly — re-deploying overwrites the previous version.
        List<DeploymentInfo> deployed = Agentspan.deploy(agent);
        System.out.println("Deployed: " + deployed);

        // ── Step 2: serve (on a daemon thread so main can keep going) ──
        Thread worker = new Thread(() -> {
            try { Agentspan.serve(agent); }
            catch (Throwable t) { /* serve() blocks; shutdown unblocks via InterruptedException */ }
        }, "example37-worker");
        worker.setDaemon(true);
        worker.start();
        // Give the worker manager a moment to register the lookupUser handler
        // with the server before we trigger an execution.
        Thread.sleep(1_500);

        // ── Step 3: start an execution and wait for the result ─────────
        AgentHandle handle = Agentspan.start(agent, "Tell me about user U001.");
        System.out.println("Started executionId=" + handle.getExecutionId());
        AgentResult result = handle.waitForResult();
        result.printResult();

        // ── Done ─────────────────────────────────────────────────────────
        Agentspan.shutdown();
        System.out.println("OK — deploy + serve + run round-trip complete.");
    }
}
