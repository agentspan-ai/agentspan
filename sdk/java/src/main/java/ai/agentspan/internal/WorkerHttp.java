// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import ai.agentspan.AgentConfig;
import ai.agentspan.exceptions.AgentAPIException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Worker-protocol HTTP calls — poll, complete, fail, register task def.
 *
 * <p>Kept separate from {@link HttpApi} (which is the user-facing agent
 * API surface) so the two concerns don't bleed into each other. Only
 * {@link WorkerManager} uses this class.
 */
public class WorkerHttp {
    private static final Logger logger = LoggerFactory.getLogger(WorkerHttp.class);

    private final AgentConfig config;
    private final HttpApi httpApi;

    public WorkerHttp(HttpApi httpApi) {
        this.httpApi = httpApi;
        this.config = httpApi.getConfig();
    }

    /**
     * {@code GET /api/tasks/poll/{taskType}} — poll for a pending task.
     *
     * <p>When {@code domain} is non-null the poll is scoped to that worker
     * domain (the read-side complement of {@code startAgent(..., runId)}).
     *
     * @return task data, or {@code null} when no task is pending
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> pollTask(String taskType, String domain) {
        try {
            String url = config.getServerUrl() + "/api/tasks/poll/" + taskType;
            if (domain != null && !domain.isEmpty()) {
                url += "?domain=" + java.net.URLEncoder.encode(domain, java.nio.charset.StandardCharsets.UTF_8);
            }
            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .GET();

            httpApi.addAuthHeaders(requestBuilder);

            HttpResponse<String> response = httpApi.getRawClient().send(
                requestBuilder.build(), HttpResponse.BodyHandlers.ofString());

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

    /** {@code POST /api/tasks} — report task completion. */
    public void completeTask(String taskId, String workflowInstanceId, Map<String, Object> output) {
        Map<String, Object> body = new HashMap<>();
        body.put("taskId", taskId);
        if (workflowInstanceId != null) body.put("workflowInstanceId", workflowInstanceId);
        body.put("status", "COMPLETED");
        body.put("outputData", output);
        httpApi.post("/api/tasks", body);
    }

    /** {@code POST /api/tasks} — report task failure. */
    public void failTask(String taskId, String workflowInstanceId, String errorMessage) {
        Map<String, Object> body = new HashMap<>();
        body.put("taskId", taskId);
        if (workflowInstanceId != null) body.put("workflowInstanceId", workflowInstanceId);
        body.put("status", "FAILED");
        body.put("reasonForIncompletion", errorMessage);
        try {
            httpApi.post("/api/tasks", body);
        } catch (Exception e) {
            logger.warn("Failed to report task failure for {}: {}", taskId, e.getMessage());
        }
    }

    /** {@code POST /api/metadata/taskdefs} — register a task definition. */
    public void registerTaskDef(String taskName) {
        Map<String, Object> taskDef = new HashMap<>();
        taskDef.put("name", taskName);
        taskDef.put("timeoutSeconds", 300);
        taskDef.put("responseTimeoutSeconds", 300);
        httpApi.post("/api/metadata/taskdefs", List.of(taskDef));
    }
}
