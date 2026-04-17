/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.*;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.AgentRuntime;

/**
 * E2E tests for DELETE on the agent definition endpoint.
 *
 * <p>Covers the path used by the UI ({@code DELETE /api/agent/definitions/{name}}) and
 * the legacy path used by the CLI ({@code DELETE /api/agent/{name}}). Boots the full
 * Spring context with in-memory SQLite and sends real HTTP requests; no mocks.</p>
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class AgentDefinitionDeleteEndpointTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    @Test
    void deleteDefinitionsPath_removesDefinition() throws Exception {
        String name = deployAgent();

        HttpURLConnection conn = delete("/api/agent/definitions/" + enc(name) + "?version=1");
        assertThat(conn.getResponseCode())
                .as("DELETE /api/agent/definitions/{name} should succeed")
                .isEqualTo(200);

        // Definition is gone — subsequent GET returns 404.
        HttpURLConnection getConn = get("/api/agent/definitions/" + enc(name));
        assertThat(getConn.getResponseCode()).isEqualTo(404);
    }

    @Test
    void deleteDefinitionsPath_withoutVersion_removesLatest() throws Exception {
        String name = deployAgent();

        HttpURLConnection conn = delete("/api/agent/definitions/" + enc(name));
        assertThat(conn.getResponseCode()).isEqualTo(200);

        HttpURLConnection getConn = get("/api/agent/definitions/" + enc(name));
        assertThat(getConn.getResponseCode()).isEqualTo(404);
    }

    @Test
    void deleteLegacyPath_stillWorks() throws Exception {
        // Backwards compatibility: the CLI uses DELETE /api/agent/{name}
        String name = deployAgent();

        HttpURLConnection conn = delete("/api/agent/" + enc(name) + "?version=1");
        assertThat(conn.getResponseCode()).isEqualTo(200);

        HttpURLConnection getConn = get("/api/agent/definitions/" + enc(name));
        assertThat(getConn.getResponseCode()).isEqualTo(404);
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    /** Deploy a minimal agent and return its unique name. */
    private String deployAgent() throws Exception {
        String name =
                "delete_test_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        Map<String, Object> config = new LinkedHashMap<>();
        config.put("name", name);
        config.put("model", "openai/gpt-4o");
        config.put("instructions", "test");
        Map<String, Object> body = Map.of("agentConfig", config);

        HttpURLConnection conn = post("/api/agent/deploy", body);
        assertThat(conn.getResponseCode())
                .as("deploy should succeed for test setup")
                .isEqualTo(200);
        conn.getInputStream().close();
        return name;
    }

    private HttpURLConnection post(String path, Map<String, Object> body) throws Exception {
        HttpURLConnection conn = open(path);
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(MAPPER.writeValueAsBytes(body));
        }
        return conn;
    }

    private HttpURLConnection delete(String path) throws Exception {
        HttpURLConnection conn = open(path);
        conn.setRequestMethod("DELETE");
        return conn;
    }

    private HttpURLConnection get(String path) throws Exception {
        HttpURLConnection conn = open(path);
        conn.setRequestMethod("GET");
        return conn;
    }

    private HttpURLConnection open(String path) throws Exception {
        URI uri = URI.create("http://localhost:" + port + path);
        return (HttpURLConnection) uri.toURL().openConnection();
    }

    private static String enc(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }
}
