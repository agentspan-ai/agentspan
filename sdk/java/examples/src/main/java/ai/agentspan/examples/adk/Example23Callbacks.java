// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.Callbacks;
import com.google.adk.agents.LlmAgent;

import io.reactivex.rxjava3.core.Maybe;

/**
 * Example Adk 23 — Callbacks (lifecycle hooks)
 *
 * <p>Java port of <code>sdk/python/examples/adk/23_callbacks.py</code>.
 *
 * <p>Demonstrates: native ADK {@code beforeModelCallback} and
 * {@code afterModelCallback} attached to an {@link LlmAgent}. The bridge
 * forwards both as Agentspan {@code CallbackHandler} workers.
 *
 * <p><b>Server-side limitation</b> (matches Python's
 * {@code 14_callbacks.py} comment): the server's workflow compiler does
 * not yet emit Conductor hook tasks for the before/after model and tool
 * callback fields on the simple-LLM agent shape. The bridge wire payload
 * is correct (verifiable via
 * {@code GET /api/workflow/{id}?includeTasks=false} — the
 * {@code agentDef.before_model_callback._worker_ref} is present in the
 * metadata) but no hook task is currently scheduled, so the worker is
 * never polled and the counters below stay at zero. Once the server
 * compiler honors callbacks, this example will start firing them
 * automatically.
 *
 * <p>When that happens, note one further constraint: the
 * {@code CallbackContext} passed to the callback is {@code null} —
 * callbacks should base decisions on the {@code LlmRequest.Builder} /
 * {@code LlmResponse} args only, not on session state. State access
 * throws NPE, which the bridge catches and logs.
 */
public class Example23Callbacks {

    // Mutable counters that the callbacks bump so we can assert from main()
    // that they actually fired end-to-end.
    private static int beforeCount = 0;
    private static int afterCount = 0;

    public static void main(String[] args) {
        Callbacks.BeforeModelCallback beforeModel = (ctx, req) -> {
            beforeCount++;
            int parts = 0;
            try {
                // best-effort — req.contents() comes from the bridge's
                // reconstruction (server-side hook payload).
                if (req.config().isPresent()) parts++;
            } catch (Throwable ignored) {}
            System.out.println("[CALLBACK] beforeModel fired (call #" + beforeCount
                    + ", req has config=" + parts + ")");
            return Maybe.empty();   // empty → continue to the LLM
        };

        Callbacks.AfterModelCallback afterModel = (ctx, response) -> {
            afterCount++;
            String text = response == null ? "" : response.content().map(c -> {
                try { return c.text(); } catch (Throwable t) { return ""; }
            }).orElse("");
            int words = text.isEmpty() ? 0 : text.split("\\s+").length;
            System.out.println("[CALLBACK] afterModel fired (call #" + afterCount
                    + ", " + words + " words in response)");
            return Maybe.empty();   // empty → use the LLM's response as-is
        };

        LlmAgent callbackAgent = LlmAgent.builder()
                .name("monitored_assistant")
                .description("Assistant instrumented with beforeModel/afterModel callbacks for monitoring.")
                .model(Settings.LLM_MODEL)
                .instruction(
                        "You are a helpful assistant. Answer questions concisely. "
                        + "Keep responses under 200 words.")
                .beforeModelCallback(beforeModel)
                .afterModelCallback(afterModel)
                .build();

        AgentResult result = Agentspan.run(callbackAgent,
                "Explain the difference between supervised and unsupervised machine learning.");
        result.printResult();

        System.out.println("\nCallback invocations: before=" + beforeCount + " after=" + afterCount);

        Agentspan.shutdown();
    }
}
