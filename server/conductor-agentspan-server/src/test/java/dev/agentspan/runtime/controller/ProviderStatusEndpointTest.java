/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.*;

import java.net.HttpURLConnection;
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.dao.SecretsDAO;

import dev.agentspan.runtime.AgentRuntime;

/**
 * GET /api/providers/status — the server is the source of truth for provider
 * configuration. Doctor (and the UI) must be able to ask the server what it
 * has, instead of guessing from the client shell's environment, which is
 * meaningless for remote/Docker/K8s deployments.
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ProviderStatusEndpointTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String ANON = "00000000-0000-0000-0000-000000000000";
    // 127.0.0.1:9 (discard port) — connection refused immediately, so the
    // reachability probe fails fast without a real Ollama.
    private static final String UNREACHABLE_URL = "http://127.0.0.1:9";

    @LocalServerPort
    private int port;

    @Autowired
    private SecretsDAO store;

    private String savedOllamaUrl;

    @BeforeEach
    void setUp() {
        savedOllamaUrl = store.getSecret("OLLAMA_BASE_URL");
        store.putSecret("OLLAMA_BASE_URL", UNREACHABLE_URL);
    }

    @AfterEach
    void cleanUp() {
        store.deleteSecret("OLLAMA_BASE_URL");
        if (savedOllamaUrl != null) store.putSecret("OLLAMA_BASE_URL", savedOllamaUrl);
    }

    private JsonNode getStatus() throws Exception {
        URI uri = URI.create("http://localhost:" + port + "/api/providers/status");
        HttpURLConnection conn = (HttpURLConnection) uri.toURL().openConnection();
        conn.setRequestMethod("GET");
        assertThat(conn.getResponseCode()).isEqualTo(200);
        return MAPPER.readTree(conn.getInputStream());
    }

    private Map<String, JsonNode> providersByName(JsonNode body) {
        assertThat(body.has("providers"))
                .as("body has providers array: %s", body)
                .isTrue();
        List<JsonNode> list = body.get("providers").findParents("name");
        return list.stream()
                .collect(java.util.stream.Collectors.toMap(n -> n.get("name").asText(), n -> n));
    }

    @Test
    void status_reportsKnownProvidersWithConfiguredFlag() throws Exception {
        Map<String, JsonNode> providers = providersByName(getStatus());

        assertThat(providers).containsKey("openai");
        assertThat(providers).containsKey("anthropic");
        assertThat(providers).containsKey("ollama");
        assertThat(providers.get("openai").has("configured")).isTrue();
    }

    @Test
    void status_ollamaReportsResolvedUrlAndServerSideReachability() throws Exception {
        Map<String, JsonNode> providers = providersByName(getStatus());
        JsonNode ollama = providers.get("ollama");

        // URL resolved from the credential store (the no-restart prod path)
        assertThat(ollama.get("baseUrl").asText()).isEqualTo(UNREACHABLE_URL);
        // Probed from the SERVER's network — the thing no client can know
        assertThat(ollama.get("reachable").asBoolean()).isFalse();
        // Credential store means it is configured
        assertThat(ollama.get("configured").asBoolean()).isTrue();
    }

    @Test
    void status_notManagedByHost_inStandaloneMode() throws Exception {
        JsonNode body = getStatus();
        assertThat(body.get("managedByHost").asBoolean()).isFalse();
    }
}
