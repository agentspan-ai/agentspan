// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.internal;

import dev.agentspan.AgentConfig;
import dev.agentspan.exceptions.AgentAPIException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Direct HTTP client for Agentspan server API calls.
 *
 * <p>Uses {@code java.net.http.HttpClient} (Java 11+) for HTTP communication.
 * All methods are synchronous and throw {@link AgentAPIException} on non-2xx responses.
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

    /**
     * Start an agent execution.
     *
     * @param agentConfig serialized agent configuration
     * @param prompt      user prompt
     * @param sessionId   optional session ID
     * @return server response containing workflowId
     */
    public Map<String, Object> startAgent(Map<String, Object> agentConfig, String prompt, String sessionId) {
        Map<String, Object> body = new HashMap<>();
        body.put("agentConfig", agentConfig);
        body.put("prompt", prompt);
        if (sessionId != null && !sessionId.isEmpty()) {
            body.put("sessionId", sessionId);
        }

        return post("/api/agent/start", body);
    }

    /**
     * Get the current status of an agent workflow.
     *
     * @param workflowId the workflow ID
     * @return status response map
     */
    public Map<String, Object> getAgentStatus(String workflowId) {
        return get("/api/agent/" + workflowId + "/status");
    }

    /**
     * Respond to a waiting agent (approve/reject a tool or send a message).
     *
     * @param workflowId the workflow ID
     * @param approved   whether to approve
     * @param reason     optional rejection reason
     */
    public void respondToAgent(String workflowId, boolean approved, String reason) {
        Map<String, Object> body = new HashMap<>();
        body.put("approved", approved);
        if (reason != null && !reason.isEmpty()) {
            body.put("reason", reason);
        }
        post("/api/agent/" + workflowId + "/respond", body);
    }

    /**
     * Send an arbitrary JSON response to a waiting agent.
     *
     * <p>Used for structured responses such as manual agent selection:
     * {@code {"selected": "writer"}}.
     *
     * @param workflowId the workflow ID
     * @param data       the response payload
     */
    public void respondWithData(String workflowId, Map<String, Object> data) {
        post("/api/agent/" + workflowId + "/respond", data);
    }

    /**
     * Poll for a pending task of the given type.
     *
     * @param taskType the task type to poll
     * @return task data or null if no pending task
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> pollTask(String taskType) {
        try {
            String url = config.getServerUrl() + "/api/tasks/poll/" + taskType;
            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .GET();

            addAuthHeaders(requestBuilder);

            HttpRequest request = requestBuilder.build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 204 || response.body() == null || response.body().isEmpty()) {
                return null;
            }

            if (response.statusCode() == 200) {
                return JsonMapper.fromJson(response.body(), Map.class);
            }

            if (response.statusCode() >= 400) {
                throw new AgentAPIException(response.statusCode(), response.body());
            }

            return null;
        } catch (AgentAPIException e) {
            throw e;
        } catch (Exception e) {
            logger.debug("Poll task failed for {}: {}", taskType, e.getMessage());
            return null;
        }
    }

    /**
     * Complete a task with output.
     *
     * @param taskId the task ID
     * @param output the output map
     */
    public void completeTask(String taskId, String workflowInstanceId, Map<String, Object> output) {
        Map<String, Object> body = new HashMap<>();
        body.put("taskId", taskId);
        if (workflowInstanceId != null) body.put("workflowInstanceId", workflowInstanceId);
        body.put("status", "COMPLETED");
        body.put("outputData", output);
        post("/api/tasks", body);
    }

    /**
     * Fail a task with an error message.
     *
     * @param taskId       the task ID
     * @param errorMessage the error message
     */
    public void failTask(String taskId, String workflowInstanceId, String errorMessage) {
        Map<String, Object> body = new HashMap<>();
        body.put("taskId", taskId);
        if (workflowInstanceId != null) body.put("workflowInstanceId", workflowInstanceId);
        body.put("status", "FAILED");
        body.put("reasonForIncompletion", errorMessage);
        try {
            post("/api/tasks", body);
        } catch (Exception e) {
            logger.warn("Failed to report task failure for {}: {}", taskId, e.getMessage());
        }
    }

    /**
     * Register a task definition on the server.
     *
     * @param taskName the task name to register
     */
    public void registerTaskDef(String taskName) {
        Map<String, Object> taskDef = new HashMap<>();
        taskDef.put("name", taskName);
        taskDef.put("timeoutSeconds", 300);
        taskDef.put("responseTimeoutSeconds", 300);
        post("/api/metadata/taskdefs", List.of(taskDef));
    }

    // ── Internal helpers ─────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private Map<String, Object> get(String path) {
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
                throw new AgentAPIException(response.statusCode(), response.body());
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

    @SuppressWarnings("unchecked")
    private Map<String, Object> post(String path, Object body) {
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
                throw new AgentAPIException(response.statusCode(), response.body());
            }

            if (response.body() == null || response.body().isEmpty()) {
                return new HashMap<>();
            }

            // Handle string responses (some endpoints return plain strings)
            String responseBody = response.body().trim();
            if (responseBody.startsWith("{")) {
                return JsonMapper.fromJson(responseBody, Map.class);
            } else if (responseBody.startsWith("\"") || (!responseBody.startsWith("[") && !responseBody.startsWith("{"))) {
                // Plain string response (e.g., workflow ID)
                Map<String, Object> result = new HashMap<>();
                result.put("workflowId", responseBody.replace("\"", ""));
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

    private void addAuthHeaders(HttpRequest.Builder builder) {
        if (config.getAuthKey() != null && !config.getAuthKey().isEmpty()) {
            builder.header("X-Auth-Key", config.getAuthKey());
        }
        if (config.getAuthSecret() != null && !config.getAuthSecret().isEmpty()) {
            builder.header("X-Auth-Secret", config.getAuthSecret());
        }
    }

    public AgentConfig getConfig() {
        return config;
    }

    public HttpClient getHttpClient() {
        return httpClient;
    }
}
