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
class EventPushEndpointTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    private int postEvent(String workflowId, Map<String, Object> body) throws Exception {
        URI uri = URI.create("http://localhost:" + port + "/api/agent/events/" + workflowId);
        HttpURLConnection conn = (HttpURLConnection) uri.toURL().openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(MAPPER.writeValueAsBytes(body));
        }
        return conn.getResponseCode();
    }

    @Test
    void pushThinkingEventReturns200() throws Exception {
        int status = postEvent("wf-test-123", Map.of(
            "type", "thinking",
            "content", "Processing node agent"
        ));
        assertThat(status).isEqualTo(200);
    }

    @Test
    void pushToolCallEventReturns200() throws Exception {
        int status = postEvent("wf-test-456", Map.of(
            "type", "tool_call",
            "toolName", "search",
            "args", Map.of("query", "test")
        ));
        assertThat(status).isEqualTo(200);
    }

    @Test
    void pushEventForUnknownWorkflowStillReturns200() throws Exception {
        int status = postEvent("nonexistent-wf", Map.of("type", "thinking", "content", "x"));
        assertThat(status).isEqualTo(200);
    }
}
