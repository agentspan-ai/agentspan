/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import dev.agentspan.runtime.AgentRuntime;
import org.junit.jupiter.api.Test;
import dev.agentspan.runtime.model.AgentSSEEvent;
import dev.agentspan.runtime.service.AgentEventListener;
import dev.agentspan.runtime.service.AgentHumanTask;
import dev.agentspan.runtime.service.AgentStreamRegistry;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.*;

/**
 * End-to-end integration test for SSE streaming over real HTTP.
 *
 * <p>Boots the full Spring context with an in-memory SQLite backend,
 * opens real HTTP connections to the SSE endpoint, and verifies events
 * arrive with correct SSE wire format.</p>
 */
@SpringBootTest(
        classes = AgentRuntime.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("test")
class AgentControllerSSEIntegrationTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    @Autowired
    private AgentStreamRegistry streamRegistry;

    @Autowired
    private AgentEventListener eventListener;

    @Autowired
    private AgentHumanTask agentHumanTask;

    private String baseUrl() {
        return "http://localhost:" + port + "/api/agent";
    }

    // ── Helpers ──────────────────────────────────────────────────────

    /** Parsed SSE event from the wire. */
    record SSEWireEvent(String id, String event, String data) {}

    /**
     * Opens a real HTTP SSE connection and collects events until the
     * connection closes or the expected count is reached.
     */
    private List<SSEWireEvent> collectSSEEvents(String workflowId, Long lastEventId,
                                                 int expectedCount, long timeoutMs) throws Exception {
        URI uri = URI.create(baseUrl() + "/stream/" + workflowId);
        HttpURLConnection conn = (HttpURLConnection) uri.toURL().openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("Accept", "text/event-stream");
        if (lastEventId != null) {
            conn.setRequestProperty("Last-Event-ID", String.valueOf(lastEventId));
        }
        conn.setConnectTimeout(5000);
        conn.setReadTimeout((int) timeoutMs);

        List<SSEWireEvent> events = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream()))) {

            String currentId = null;
            String currentEvent = null;
            StringBuilder currentData = new StringBuilder();
            String line;

            while ((line = reader.readLine()) != null) {
                if (line.startsWith("id:")) {
                    currentId = line.substring(3);
                } else if (line.startsWith("event:")) {
                    currentEvent = line.substring(6);
                } else if (line.startsWith("data:")) {
                    if (currentData.length() > 0) currentData.append("\n");
                    currentData.append(line.substring(5));
                } else if (line.isEmpty()) {
                    // Empty line = event boundary
                    if (currentEvent != null || currentData.length() > 0) {
                        events.add(new SSEWireEvent(currentId, currentEvent, currentData.toString()));
                        currentId = null;
                        currentEvent = null;
                        currentData.setLength(0);
                    }
                    if (events.size() >= expectedCount) {
                        break;
                    }
                }
                // Skip comment lines (heartbeats)
            }
        } finally {
            conn.disconnect();
        }
        return events;
    }

    // ── Tests ────────────────────────────────────────────────────────

    @Test
    void healthEndpointReturnsHello() throws Exception {
        HttpURLConnection conn = (HttpURLConnection)
                URI.create(baseUrl()).toURL().openConnection();
        conn.setRequestMethod("GET");
        assertThat(conn.getResponseCode()).isEqualTo(200);
        String body = new String(conn.getInputStream().readAllBytes());
        assertThat(body).isEqualTo("Hello, Agent!");
        conn.disconnect();
    }

    @Test
    void sseEndpointReturnsEventStream() throws Exception {
        String wfId = "e2e-test-content-type";

        // Pre-buffer an event and then complete so the stream will close
        streamRegistry.send(wfId, AgentSSEEvent.done(wfId, "result"));

        CompletableFuture<Void> completer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(200); } catch (InterruptedException ignored) {}
            streamRegistry.complete(wfId);
        });

        List<SSEWireEvent> events = collectSSEEvents(wfId, 0L, 1, 5000);
        completer.join();

        assertThat(events).isNotEmpty();
        SSEWireEvent first = events.get(0);
        assertThat(first.event()).isEqualTo("done");
        assertThat(first.id()).isEqualTo("1");
    }

    @Test
    void sseDeliversAllEventTypes() throws Exception {
        String wfId = "e2e-test-all-events";

        // Async: send events after a short delay to allow client to connect
        CompletableFuture<Void> producer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(300); } catch (InterruptedException ignored) {}
            streamRegistry.send(wfId, AgentSSEEvent.thinking(wfId, "agent_llm"));
            streamRegistry.send(wfId, AgentSSEEvent.toolCall(wfId, "search", Map.of("q", "hello")));
            streamRegistry.send(wfId, AgentSSEEvent.toolResult(wfId, "search", "found it"));
            streamRegistry.send(wfId, AgentSSEEvent.guardrailPass(wfId, "safety_check"));
            streamRegistry.send(wfId, AgentSSEEvent.handoff(wfId, "support"));
            streamRegistry.send(wfId, AgentSSEEvent.waiting(wfId, Map.of("tool_name", "approve")));
            streamRegistry.send(wfId, AgentSSEEvent.error(wfId, "task1", "oops"));
            streamRegistry.send(wfId, AgentSSEEvent.done(wfId, Map.of("result", "Final")));
            streamRegistry.complete(wfId);
        });

        List<SSEWireEvent> events = collectSSEEvents(wfId, null, 8, 10000);
        producer.join();

        assertThat(events).hasSize(8);

        // Verify each event type and sequential IDs
        assertThat(events.get(0).event()).isEqualTo("thinking");
        assertThat(events.get(0).id()).isEqualTo("1");

        assertThat(events.get(1).event()).isEqualTo("tool_call");
        assertThat(events.get(1).id()).isEqualTo("2");

        assertThat(events.get(2).event()).isEqualTo("tool_result");
        assertThat(events.get(2).id()).isEqualTo("3");

        assertThat(events.get(3).event()).isEqualTo("guardrail_pass");
        assertThat(events.get(3).id()).isEqualTo("4");

        assertThat(events.get(4).event()).isEqualTo("handoff");
        assertThat(events.get(4).id()).isEqualTo("5");

        assertThat(events.get(5).event()).isEqualTo("waiting");
        assertThat(events.get(5).id()).isEqualTo("6");

        assertThat(events.get(6).event()).isEqualTo("error");
        assertThat(events.get(6).id()).isEqualTo("7");

        assertThat(events.get(7).event()).isEqualTo("done");
        assertThat(events.get(7).id()).isEqualTo("8");

        // Verify JSON payload for tool_call
        JsonNode toolCallData = MAPPER.readTree(events.get(1).data());
        assertThat(toolCallData.get("toolName").asText()).isEqualTo("search");
        assertThat(toolCallData.get("args").get("q").asText()).isEqualTo("hello");

        // Verify JSON payload for done
        JsonNode doneData = MAPPER.readTree(events.get(7).data());
        assertThat(doneData.get("output").get("result").asText()).isEqualTo("Final");
    }

    @Test
    void sseReconnectionReplaysFromLastEventId() throws Exception {
        String wfId = "e2e-test-reconnect";

        // Pre-buffer 5 events
        streamRegistry.send(wfId, AgentSSEEvent.thinking(wfId, "llm"));
        streamRegistry.send(wfId, AgentSSEEvent.toolCall(wfId, "search", null));
        streamRegistry.send(wfId, AgentSSEEvent.toolResult(wfId, "search", "data"));
        streamRegistry.send(wfId, AgentSSEEvent.guardrailPass(wfId, "guard"));
        streamRegistry.send(wfId, AgentSSEEvent.done(wfId, "output"));

        // Complete after a delay so client can read replayed events
        CompletableFuture<Void> completer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(500); } catch (InterruptedException ignored) {}
            streamRegistry.complete(wfId);
        });

        // Reconnect with Last-Event-ID: 3 → should get events 4 and 5
        List<SSEWireEvent> events = collectSSEEvents(wfId, 3L, 2, 5000);
        completer.join();

        assertThat(events).hasSize(2);
        assertThat(events.get(0).id()).isEqualTo("4");
        assertThat(events.get(0).event()).isEqualTo("guardrail_pass");
        assertThat(events.get(1).id()).isEqualTo("5");
        assertThat(events.get(1).event()).isEqualTo("done");
    }

    @Test
    void sseSubWorkflowAliasForwardsEvents() throws Exception {
        String parentWfId = "e2e-test-parent";
        String childWfId = "e2e-test-child";

        // Register alias: child → parent
        streamRegistry.registerAlias(childWfId, parentWfId);

        // Async: send events from both parent and child
        CompletableFuture<Void> producer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(300); } catch (InterruptedException ignored) {}
            streamRegistry.send(parentWfId, AgentSSEEvent.thinking(parentWfId, "parent_llm"));
            streamRegistry.send(childWfId, AgentSSEEvent.thinking(childWfId, "child_llm"));
            streamRegistry.send(childWfId, AgentSSEEvent.toolCall(childWfId, "child_tool", null));
            streamRegistry.send(parentWfId, AgentSSEEvent.done(parentWfId, "result"));
            streamRegistry.complete(parentWfId);
        });

        // Client connects to parent — should see all events (including child's)
        List<SSEWireEvent> events = collectSSEEvents(parentWfId, null, 4, 10000);
        producer.join();

        assertThat(events).hasSize(4);
        // All events should have sequential IDs in the parent's sequence
        assertThat(events.get(0).id()).isEqualTo("1");
        assertThat(events.get(1).id()).isEqualTo("2");
        assertThat(events.get(2).id()).isEqualTo("3");
        assertThat(events.get(3).id()).isEqualTo("4");

        // Verify child events were forwarded
        assertThat(events.get(1).event()).isEqualTo("thinking");
        assertThat(events.get(2).event()).isEqualTo("tool_call");
    }

    @Test
    void sseMultipleClientsReceiveSameEvents() throws Exception {
        String wfId = "e2e-test-multi-client";
        CountDownLatch clientsReady = new CountDownLatch(2);

        // Two clients connect concurrently
        CompletableFuture<List<SSEWireEvent>> client1 = CompletableFuture.supplyAsync(() -> {
            clientsReady.countDown();
            try {
                return collectSSEEvents(wfId, null, 3, 10000);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });

        CompletableFuture<List<SSEWireEvent>> client2 = CompletableFuture.supplyAsync(() -> {
            clientsReady.countDown();
            try {
                return collectSSEEvents(wfId, null, 3, 10000);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });

        // Wait for clients to start, then send events
        clientsReady.await(3, TimeUnit.SECONDS);
        Thread.sleep(500); // Give HTTP connections time to establish

        streamRegistry.send(wfId, AgentSSEEvent.thinking(wfId, "llm"));
        streamRegistry.send(wfId, AgentSSEEvent.toolCall(wfId, "search", null));
        streamRegistry.send(wfId, AgentSSEEvent.done(wfId, "result"));
        streamRegistry.complete(wfId);

        List<SSEWireEvent> events1 = client1.get(10, TimeUnit.SECONDS);
        List<SSEWireEvent> events2 = client2.get(10, TimeUnit.SECONDS);

        // Both clients should receive the same 3 events
        assertThat(events1).hasSize(3);
        assertThat(events2).hasSize(3);

        for (int i = 0; i < 3; i++) {
            assertThat(events1.get(i).id()).isEqualTo(events2.get(i).id());
            assertThat(events1.get(i).event()).isEqualTo(events2.get(i).event());
        }
    }

    @Test
    void sseGuardrailFailIncludesMessage() throws Exception {
        String wfId = "e2e-test-guardrail-fail";

        CompletableFuture<Void> producer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(300); } catch (InterruptedException ignored) {}
            streamRegistry.send(wfId,
                    AgentSSEEvent.guardrailFail(wfId, "pii_filter", "SSN detected in output"));
            streamRegistry.send(wfId, AgentSSEEvent.done(wfId, null));
            streamRegistry.complete(wfId);
        });

        List<SSEWireEvent> events = collectSSEEvents(wfId, null, 2, 10000);
        producer.join();

        assertThat(events).hasSize(2);
        assertThat(events.get(0).event()).isEqualTo("guardrail_fail");

        JsonNode payload = MAPPER.readTree(events.get(0).data());
        assertThat(payload.get("guardrailName").asText()).isEqualTo("pii_filter");
        assertThat(payload.get("content").asText()).isEqualTo("SSN detected in output");
    }

    @Test
    void sseWaitingEventIncludesPendingToolInfo() throws Exception {
        String wfId = "e2e-test-waiting";

        CompletableFuture<Void> producer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(300); } catch (InterruptedException ignored) {}
            Map<String, Object> pending = Map.of(
                    "tool_name", "approve_purchase",
                    "parameters", Map.of("amount", 500),
                    "taskRefName", "hitl_approve"
            );
            streamRegistry.send(wfId, AgentSSEEvent.waiting(wfId, pending));
            streamRegistry.send(wfId, AgentSSEEvent.done(wfId, "approved"));
            streamRegistry.complete(wfId);
        });

        List<SSEWireEvent> events = collectSSEEvents(wfId, null, 2, 10000);
        producer.join();

        JsonNode waitPayload = MAPPER.readTree(events.get(0).data());
        assertThat(waitPayload.get("type").asText()).isEqualTo("waiting");
        assertThat(waitPayload.get("pendingTool").get("tool_name").asText())
                .isEqualTo("approve_purchase");
        assertThat(waitPayload.get("pendingTool").get("parameters").get("amount").asInt())
                .isEqualTo(500);
    }

    @Test
    void sseFirstConnectReplaysBufferedEvents() throws Exception {
        String wfId = "e2e-test-first-connect-replay";

        // Buffer events BEFORE any client connects
        streamRegistry.send(wfId, AgentSSEEvent.thinking(wfId, "llm"));
        streamRegistry.send(wfId, AgentSSEEvent.toolCall(wfId, "search", Map.of("q", "test")));
        streamRegistry.send(wfId, AgentSSEEvent.toolResult(wfId, "search", "result"));

        // Complete after delay so client can read replayed + new events
        CompletableFuture<Void> completer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(500); } catch (InterruptedException ignored) {}
            streamRegistry.send(wfId, AgentSSEEvent.done(wfId, "Final"));
            streamRegistry.complete(wfId);
        });

        // First connect (no Last-Event-ID) — should replay all 3 buffered + receive 1 new
        List<SSEWireEvent> events = collectSSEEvents(wfId, null, 4, 10000);
        completer.join();

        assertThat(events).hasSize(4);
        assertThat(events.get(0).event()).isEqualTo("thinking");
        assertThat(events.get(0).id()).isEqualTo("1");
        assertThat(events.get(1).event()).isEqualTo("tool_call");
        assertThat(events.get(1).id()).isEqualTo("2");
        assertThat(events.get(2).event()).isEqualTo("tool_result");
        assertThat(events.get(2).id()).isEqualTo("3");
        assertThat(events.get(3).event()).isEqualTo("done");
        assertThat(events.get(3).id()).isEqualTo("4");
    }

    @Test
    void sseHumanTaskScheduledEmitsWaitingImmediately() throws Exception {
        String wfId = "e2e-test-human-waiting";

        // Simulate full event lifecycle through the real AgentEventListener
        CompletableFuture<Void> producer = CompletableFuture.runAsync(() -> {
            try { Thread.sleep(300); } catch (InterruptedException ignored) {}

            // 1. LLM_CHAT_COMPLETE scheduled → thinking event
            TaskModel llmTask = new TaskModel();
            llmTask.setWorkflowInstanceId(wfId);
            llmTask.setTaskType("LLM_CHAT_COMPLETE");
            llmTask.setReferenceTaskName("agent_llm");
            eventListener.onTaskScheduled(llmTask);

            // 2. HUMAN task starts → AgentHumanTask emits waiting event immediately
            WorkflowModel humanWf = new WorkflowModel();
            humanWf.setWorkflowId(wfId);
            TaskModel humanTask = new TaskModel();
            humanTask.setReferenceTaskName("hitl_approve");
            humanTask.setInputData(Map.of(
                    "tool_name", "publish_article",
                    "parameters", Map.of("title", "Test Article")
            ));
            agentHumanTask.start(humanWf, humanTask, null);

            // 3. Workflow completes after approval
            try { Thread.sleep(200); } catch (InterruptedException ignored) {}
            WorkflowModel wf = new WorkflowModel();
            wf.setWorkflowId(wfId);
            wf.setOutput(Map.of("result", "Published"));
            eventListener.onWorkflowCompletedIfEnabled(wf);
        });

        List<SSEWireEvent> events = collectSSEEvents(wfId, null, 3, 10000);
        producer.join();

        assertThat(events).hasSize(3);

        // 1. thinking (LLM scheduled)
        assertThat(events.get(0).event()).isEqualTo("thinking");

        // 2. waiting (HUMAN scheduled — immediate, no 30s delay)
        assertThat(events.get(1).event()).isEqualTo("waiting");
        JsonNode waitData = MAPPER.readTree(events.get(1).data());
        assertThat(waitData.get("pendingTool").get("tool_name").asText()).isEqualTo("publish_article");
        assertThat(waitData.get("pendingTool").get("taskRefName").asText()).isEqualTo("hitl_approve");

        // 3. done (workflow completed)
        assertThat(events.get(2).event()).isEqualTo("done");
        JsonNode doneData = MAPPER.readTree(events.get(2).data());
        assertThat(doneData.get("output").get("result").asText()).isEqualTo("Published");
    }
}
