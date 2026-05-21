// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import ai.agentspan.AgentConfig;
import ai.agentspan.exceptions.AgentAPIException;
import ai.agentspan.exceptions.AgentNotFoundException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/**
 * HTTP client for the Agent Runtime API.
 *
 * <p>Mirrors the Python SDK's {@code AgentHttpClient}: one method per
 * server endpoint, payload-shaped by the caller. Worker-protocol calls
 * (poll / complete / fail / register) live in {@link WorkerHttp}.
 */
public class HttpApi {
    private static final Logger logger = LoggerFactory.getLogger(HttpApi.class);

    private final AgentConfig config;
    private final HttpClient httpClient;

    public HttpApi(AgentConfig config) {
        this.config = config;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();
    }

    /** {@code POST /api/agent/start} — start an agent execution. */
    public Map<String, Object> startAgent(Map<String, Object> payload) {
        return post("/api/agent/start", payload);
    }

    /** {@code POST /api/agent/compile} — compile agent config to workflow def. */
    public Map<String, Object> compileAgent(Map<String, Object> payload) {
        return post("/api/agent/compile", payload);
    }

    /** {@code POST /api/agent/deploy} — deploy (compile + register, no execution). */
    public Map<String, Object> deployAgent(Map<String, Object> payload) {
        return post("/api/agent/deploy", payload);
    }

    /** {@code GET /api/agent/{id}/status} — fetch execution status. */
    public Map<String, Object> getAgentStatus(String executionId) {
        return get("/api/agent/" + executionId + "/status");
    }

    /** {@code POST /api/agent/{id}/respond} — respond to a waiting agent. */
    public void respond(String executionId, Map<String, Object> body) {
        post("/api/agent/" + executionId + "/respond", body);
    }

    /** {@code GET /api/workflow/{id}} — fetch raw workflow data (tasks, domain, run_id). */
    public Map<String, Object> getWorkflow(String executionId) {
        return get("/api/workflow/" + executionId);
    }

    // ── Internal helpers ─────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    Map<String, Object> get(String path) {
        try {
            String url = config.getServerUrl() + path;
            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .GET()
                .header("Content-Type", "application/json");

            addAuthHeaders(requestBuilder);

            HttpRequest request = requestBuilder.build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() >= 400) {
                throw apiError(response.statusCode(), response.body());
            }

            if (response.body() == null || response.body().isEmpty()) {
                return new HashMap<>();
            }

            return JsonMapper.fromJson(response.body(), Map.class);
        } catch (AgentAPIException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("HTTP GET failed: " + path, e);
        }
    }

    private static AgentAPIException apiError(int statusCode, String body) {
        if (statusCode == 404) {
            return new AgentNotFoundException(statusCode, body);
        }
        return new AgentAPIException(statusCode, body);
    }

    @SuppressWarnings("unchecked")
    Map<String, Object> post(String path, Object body) {
        try {
            String url = config.getServerUrl() + path;
            String jsonBody = JsonMapper.toJson(body);

            logger.debug("POST {} body: {}", url, jsonBody);

            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                .header("Content-Type", "application/json");

            addAuthHeaders(requestBuilder);

            HttpRequest request = requestBuilder.build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            logger.debug("POST {} -> {} {}", url, response.statusCode(), response.body());

            if (response.statusCode() >= 400) {
                throw apiError(response.statusCode(), response.body());
            }

            if (response.body() == null || response.body().isEmpty()) {
                return new HashMap<>();
            }

            String responseBody = response.body().trim();
            if (responseBody.startsWith("{")) {
                return JsonMapper.fromJson(responseBody, Map.class);
            } else if (responseBody.startsWith("\"") || (!responseBody.startsWith("[") && !responseBody.startsWith("{"))) {
                Map<String, Object> result = new HashMap<>();
                result.put("executionId", responseBody.replace("\"", ""));
                return result;
            } else {
                return JsonMapper.fromJson(responseBody, Map.class);
            }
        } catch (AgentAPIException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("HTTP POST failed: " + path, e);
        }
    }

    void addAuthHeaders(HttpRequest.Builder builder) {
        if (config.getAuthKey() != null && !config.getAuthKey().isEmpty()) {
            builder.header("X-Auth-Key", config.getAuthKey());
        }
        if (config.getAuthSecret() != null && !config.getAuthSecret().isEmpty()) {
            builder.header("X-Auth-Secret", config.getAuthSecret());
        }
    }

    AgentConfig getConfig() {
        return config;
    }

    HttpClient getRawClient() {
        return httpClient;
    }

    public HttpClient getHttpClient() {
        return httpClient;
    }
}
