/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.*;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.AgentRuntime;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class AgentDagEndpointTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    @Test
    void createTrackingExecution_returns200WithExecutionId() throws Exception {
        Map<String, Object> body = Map.of("workflowName", "test-sub-agent", "input", Map.of("prompt", "do the thing"));

        HttpURLConnection conn = post("/api/agent/execution", body);
        assertThat(conn.getResponseCode()).isEqualTo(200);

        Map<?, ?> resp = MAPPER.readValue(conn.getInputStream(), Map.class);
        assertThat(resp.get("executionId")).isNotNull().asString().isNotBlank();
    }

    @Test
    void injectTask_returns200WithTaskId() throws Exception {
        // First create a tracking workflow to inject into
        String executionId = createTrackingExecution();

        Map<String, Object> body = Map.of(
                "taskDefName", "Bash",
                "referenceTaskName", "bash_ref_1",
                "type", "SIMPLE",
                "inputData", Map.of("command", "ls"),
                "status", "IN_PROGRESS");

        HttpURLConnection conn = post("/api/agent/" + executionId + "/tasks", body);
        assertThat(conn.getResponseCode()).isEqualTo(200);

        Map<?, ?> resp = MAPPER.readValue(conn.getInputStream(), Map.class);
        assertThat(resp.get("taskId")).isNotNull().asString().isNotBlank();
    }

    @Test
    void injectTask_unknownWorkflow_returns404() throws Exception {
        Map<String, Object> body = Map.of(
                "taskDefName", "Bash",
                "referenceTaskName", "bash_ref_1",
                "type", "SIMPLE");

        HttpURLConnection conn = post("/api/agent/nonexistent-workflow-id-xyz/tasks", body);
        assertThat(conn.getResponseCode()).isEqualTo(404);
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    private String createTrackingExecution() throws Exception {
        Map<String, Object> body = Map.of("workflowName", "test-sub-agent", "input", Map.of("prompt", "run"));
        HttpURLConnection conn = post("/api/agent/execution", body);
        Map<?, ?> resp = MAPPER.readValue(conn.getInputStream(), Map.class);
        return (String) resp.get("executionId");
    }

    private HttpURLConnection post(String path, Map<String, Object> body) throws Exception {
        URI uri = URI.create("http://localhost:" + port + path);
        HttpURLConnection conn = (HttpURLConnection) uri.toURL().openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(MAPPER.writeValueAsBytes(body));
        }
        return conn;
    }
}
