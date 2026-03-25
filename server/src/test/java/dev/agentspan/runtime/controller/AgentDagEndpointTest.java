/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.agentspan.runtime.AgentRuntime;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest(
        classes = AgentRuntime.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("test")
class AgentDagEndpointTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    @Test
    void createTrackingWorkflow_returns200WithWorkflowId() throws Exception {
        Map<String, Object> body = Map.of(
                "workflowName", "test-sub-agent",
                "input", Map.of("prompt", "do the thing")
        );

        HttpURLConnection conn = post("/api/agent/workflow", body);
        assertThat(conn.getResponseCode()).isEqualTo(200);

        Map<?, ?> resp = MAPPER.readValue(conn.getInputStream(), Map.class);
        assertThat(resp.get("workflowId")).isNotNull().asString().isNotBlank();
    }

    @Test
    void injectTask_returns200WithTaskId() throws Exception {
        // First create a tracking workflow to inject into
        String workflowId = createTrackingWorkflow();

        Map<String, Object> body = Map.of(
                "taskDefName", "Bash",
                "referenceTaskName", "bash_ref_1",
                "type", "SIMPLE",
                "inputData", Map.of("command", "ls"),
                "status", "IN_PROGRESS"
        );

        HttpURLConnection conn = post("/api/agent/" + workflowId + "/tasks", body);
        assertThat(conn.getResponseCode()).isEqualTo(200);

        Map<?, ?> resp = MAPPER.readValue(conn.getInputStream(), Map.class);
        assertThat(resp.get("taskId")).isNotNull().asString().isNotBlank();
    }

    @Test
    void injectTask_unknownWorkflow_returns404() throws Exception {
        Map<String, Object> body = Map.of(
                "taskDefName", "Bash",
                "referenceTaskName", "bash_ref_1",
                "type", "SIMPLE"
        );

        HttpURLConnection conn = post("/api/agent/nonexistent-workflow-id-xyz/tasks", body);
        assertThat(conn.getResponseCode()).isEqualTo(404);
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    private String createTrackingWorkflow() throws Exception {
        Map<String, Object> body = Map.of(
                "workflowName", "test-sub-agent",
                "input", Map.of("prompt", "run")
        );
        HttpURLConnection conn = post("/api/agent/workflow", body);
        Map<?, ?> resp = MAPPER.readValue(conn.getInputStream(), Map.class);
        return (String) resp.get("workflowId");
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
