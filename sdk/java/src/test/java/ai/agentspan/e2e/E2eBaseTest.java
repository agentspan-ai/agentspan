// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.e2e;

import org.junit.jupiter.api.BeforeAll;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.fail;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * Base class for all e2e tests.
 *
 * <p>Provides:
 * <ul>
 *   <li>Server health check that skips tests if server is not available</li>
 *   <li>Helper methods to fetch workflow data from the server</li>
 *   <li>Helper to extract agentDef from a plan() result</li>
 * </ul>
 */
public abstract class E2eBaseTest {

    /** API URL for the Agentspan server (includes /api suffix). */
    protected static final String SERVER_URL =
        System.getenv().getOrDefault("AGENTSPAN_SERVER_URL", "http://localhost:6767/api");

    /** Base URL (without /api) for health checks and workflow fetches. */
    protected static final String BASE_URL = SERVER_URL.replace("/api", "");

    /** LLM model to use in e2e tests. */
    protected static final String MODEL =
        System.getenv().getOrDefault("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini");

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /**
     * Check that the server is available before any tests in the class run.
     * If the server is not reachable or unhealthy, all tests in the class are skipped.
     */
    @BeforeAll
    static void checkServerHealth() {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/health"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
            HttpResponse<String> response = HTTP_CLIENT.send(request,
                HttpResponse.BodyHandlers.ofString());

            boolean healthy = false;
            if (response.statusCode() == 200 && response.body() != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> body = MAPPER.readValue(response.body(), Map.class);
                Object h = body.get("healthy");
                healthy = Boolean.TRUE.equals(h);
            }
            assumeTrue(healthy,
                "Server at " + BASE_URL + " is not healthy — skipping e2e tests");
        } catch (Exception e) {
            assumeTrue(false,
                "Server not available at " + BASE_URL + ": " + e.getMessage());
        }
    }

    /**
     * Fetch a full workflow execution from the server.
     *
     * @param workflowId the workflow execution ID
     * @return the workflow data map
     */
    @SuppressWarnings("unchecked")
    protected Map<String, Object> getWorkflow(String workflowId) {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/api/workflow/" + workflowId))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
            HttpResponse<String> response = HTTP_CLIENT.send(request,
                HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 400) {
                fail("Failed to fetch workflow " + workflowId + ": HTTP " + response.statusCode());
            }
            return MAPPER.readValue(response.body(), Map.class);
        } catch (Exception e) {
            fail("Failed to fetch workflow " + workflowId + ": " + e.getMessage());
            return null; // unreachable
        }
    }

    /**
     * Extract agentDef from a plan() result.
     *
     * <p>Navigates: {@code plan → workflowDef → metadata → agentDef}.
     * Fails with a clear message if any key is missing.
     *
     * @param plan the plan() result map
     * @return the agentDef map
     */
    @SuppressWarnings("unchecked")
    protected Map<String, Object> getAgentDef(Map<String, Object> plan) {
        Object wfObj = plan.get("workflowDef");
        if (wfObj == null) {
            fail("plan() result missing 'workflowDef'. Top-level keys: " + plan.keySet());
        }
        Map<String, Object> wf = (Map<String, Object>) wfObj;

        Object metaObj = wf.get("metadata");
        if (metaObj == null) {
            fail("workflowDef missing 'metadata'. workflowDef keys: " + wf.keySet());
        }
        Map<String, Object> metadata = (Map<String, Object>) metaObj;

        Object agentDefObj = metadata.get("agentDef");
        if (agentDefObj == null) {
            fail("workflowDef.metadata missing 'agentDef'. metadata keys: " + metadata.keySet());
        }
        return (Map<String, Object>) agentDefObj;
    }

    /**
     * Recursively collect all tasks from a workflow definition.
     *
     * <p>Traverses nested structures: DO_WHILE loopOver, SWITCH decisionCases/
     * defaultCase, FORK_JOIN forkTasks.
     *
     * @param workflowDef the workflowDef map
     * @return flat list of all tasks
     */
    @SuppressWarnings("unchecked")
    protected List<Map<String, Object>> allTasksFlat(Map<String, Object> workflowDef) {
        java.util.List<Map<String, Object>> result = new java.util.ArrayList<>();
        Object tasksObj = workflowDef.get("tasks");
        if (!(tasksObj instanceof List)) return result;
        for (Object t : (List<?>) tasksObj) {
            if (t instanceof Map) {
                Map<String, Object> task = (Map<String, Object>) t;
                result.add(task);
                result.addAll(recurseTask(task));
            }
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> recurseTask(Map<String, Object> task) {
        java.util.List<Map<String, Object>> children = new java.util.ArrayList<>();

        // DO_WHILE loopOver
        Object loopOver = task.get("loopOver");
        if (loopOver instanceof List) {
            for (Object t : (List<?>) loopOver) {
                if (t instanceof Map) {
                    Map<String, Object> child = (Map<String, Object>) t;
                    children.add(child);
                    children.addAll(recurseTask(child));
                }
            }
        }

        // SWITCH decisionCases
        Object decisionCases = task.get("decisionCases");
        if (decisionCases instanceof Map) {
            for (Object caseTasksObj : ((Map<?, ?>) decisionCases).values()) {
                if (caseTasksObj instanceof List) {
                    for (Object ct : (List<?>) caseTasksObj) {
                        if (ct instanceof Map) {
                            Map<String, Object> child = (Map<String, Object>) ct;
                            children.add(child);
                            children.addAll(recurseTask(child));
                        }
                    }
                }
            }
        }

        // defaultCase
        Object defaultCase = task.get("defaultCase");
        if (defaultCase instanceof List) {
            for (Object t : (List<?>) defaultCase) {
                if (t instanceof Map) {
                    Map<String, Object> child = (Map<String, Object>) t;
                    children.add(child);
                    children.addAll(recurseTask(child));
                }
            }
        }

        // FORK_JOIN forkTasks
        Object forkTasks = task.get("forkTasks");
        if (forkTasks instanceof List) {
            for (Object forkList : (List<?>) forkTasks) {
                if (forkList instanceof List) {
                    for (Object ft : (List<?>) forkList) {
                        if (ft instanceof Map) {
                            Map<String, Object> child = (Map<String, Object>) ft;
                            children.add(child);
                            children.addAll(recurseTask(child));
                        }
                    }
                }
            }
        }

        return children;
    }
}
