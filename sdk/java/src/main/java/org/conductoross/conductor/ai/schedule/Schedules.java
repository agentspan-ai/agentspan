// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.schedule;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.conductoross.conductor.ai.exceptions.AgentAPIException;
import org.conductoross.conductor.ai.model.AgentHandle;
import org.conductoross.conductor.ai.model.AgentResult;

import com.fasterxml.jackson.core.type.TypeReference;
import com.netflix.conductor.client.exception.ConductorClientException;
import com.netflix.conductor.client.http.ConductorClient;
import com.netflix.conductor.client.http.ConductorClientRequest;
import com.netflix.conductor.client.http.ConductorClientRequest.Method;
import com.netflix.conductor.client.http.WorkflowClient;
import com.netflix.conductor.common.metadata.workflow.StartWorkflowRequest;
import com.netflix.conductor.common.run.Workflow;

/**
 * Lifecycle API for cron-based agent schedules. Obtained via {@code runtime.schedules()}.
 *
 * <p>All requests ride the shared native Conductor {@link ConductorClient}/ApiClient
 * (same HTTP + token-auth backend as every other client) — the scheduler CRUD via
 * {@link ConductorClientRequest}/{@link ConductorClient#execute} ({@code /api/scheduler/*},
 * for which the Conductor client ships no typed {@code SchedulerClient}), and
 * {@code runNow} via the typed {@link WorkflowClient}.
 *
 * <p>Operations are keyed by the <strong>wire name</strong> (prefixed with
 * {@code agent-}) returned by {@link #list(String)}. Use {@link Schedule} to
 * construct the user-facing short name; the SDK prefixes it at deploy time.
 */
public class Schedules {

    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<Map<String, Object>>() {};
    private static final TypeReference<List<Map<String, Object>>> LIST_MAP_TYPE =
            new TypeReference<List<Map<String, Object>>>() {};
    private static final TypeReference<List<Long>> LIST_LONG_TYPE = new TypeReference<List<Long>>() {};

    private final ConductorClient client;
    /** Shared native Conductor client for starting workflows (runNow). */
    private final WorkflowClient workflowClient;

    public Schedules(ConductorClient conductorClient) {
        this.client = conductorClient;
        this.workflowClient = new WorkflowClient(conductorClient);
    }

    /** Test seam: inject a {@link WorkflowClient} so {@code runNow}/{@code runNowAndWait} can be unit-tested. */
    Schedules(ConductorClient conductorClient, WorkflowClient workflowClient) {
        this.client = conductorClient;
        this.workflowClient = workflowClient;
    }

    // ── CRUD ────────────────────────────────────────────────────────────

    public void save(Schedule schedule, String agentName) {
        Map<String, Object> body = toSaveRequest(schedule, agentName);
        execVoid(ConductorClientRequest.builder()
                .method(Method.POST)
                .path("/scheduler/schedules")
                .body(body)
                .build());
    }

    public ScheduleInfo get(String wireName) {
        Map<String, Object> resp = exec(
                ConductorClientRequest.builder()
                        .method(Method.GET)
                        .path("/scheduler/schedules/{name}")
                        .addPathParam("name", wireName)
                        .build(),
                MAP_TYPE);
        if (resp == null || resp.isEmpty() || resp.get("name") == null) {
            throw new ScheduleException.NotFound("Schedule '" + wireName + "' not found");
        }
        return fromWorkflowSchedule(resp, null);
    }

    public List<ScheduleInfo> list(String agentName) {
        List<Map<String, Object>> resp = exec(
                ConductorClientRequest.builder()
                        .method(Method.GET)
                        .path("/scheduler/schedules")
                        .addQueryParam("workflowName", agentName)
                        .build(),
                LIST_MAP_TYPE);
        if (resp == null) return new ArrayList<>();
        List<ScheduleInfo> out = new ArrayList<>();
        for (Map<String, Object> item : resp) {
            if (item != null) out.add(fromWorkflowSchedule(item, agentName));
        }
        return out;
    }

    public void pause(String wireName) {
        pause(wireName, null);
    }

    public void pause(String wireName, String reason) {
        ConductorClientRequest.Builder b = ConductorClientRequest.builder()
                .method(Method.PUT)
                .path("/scheduler/schedules/{name}/pause")
                .addPathParam("name", wireName);
        if (reason != null) b.addQueryParam("reason", reason);
        execVoid(b.build());
    }

    public void resume(String wireName) {
        execVoid(ConductorClientRequest.builder()
                .method(Method.PUT)
                .path("/scheduler/schedules/{name}/resume")
                .addPathParam("name", wireName)
                .build());
    }

    public void delete(String wireName) {
        execVoid(ConductorClientRequest.builder()
                .method(Method.DELETE)
                .path("/scheduler/schedules/{name}")
                .addPathParam("name", wireName)
                .build());
    }

    /**
     * Start the scheduled agent's workflow immediately via the official Conductor
     * {@link WorkflowClient#startWorkflow} (returns the new workflowId).
     */
    public String runNow(ScheduleInfo info) {
        StartWorkflowRequest req = new StartWorkflowRequest();
        req.setName(info.getAgent());
        if (info.getInput() != null) req.setInput(info.getInput());
        return workflowClient.startWorkflow(req);
    }

    /** Default timeout (ms) for {@link #runNowAndWait}, mirroring Python's 600s default. */
    private static final long DEFAULT_WAIT_TIMEOUT_MS = 600_000L;
    /** Default poll interval (ms) for {@link #runNowAndWait}, mirroring Python's 1s default. */
    private static final long DEFAULT_POLL_INTERVAL_MS = 1_000L;

    /**
     * Fetch the schedule by its wire {@code name} and start its agent's workflow
     * immediately with the schedule's stored input. Returns the new workflowId.
     *
     * <p>Name-keyed parity with the Python/TS {@code run_now(name)}.
     */
    public String runNow(String name) {
        return runNow(get(name));
    }

    /**
     * Fetch the schedule by its wire {@code name} and start its agent's workflow.
     *
     * <p>When {@code wait} is {@code false} (default behaviour) returns the
     * workflowId immediately. When {@code wait} is {@code true} this blocks until
     * the workflow reaches a terminal state and returns an {@link AgentResult}
     * built from the completed workflow (parity with Python's
     * {@code run_now(name, wait=True)} and the C#/TS SDKs, which return an
     * {@link AgentResult} from the wait variant).
     *
     * @return a {@link String} workflowId when {@code wait=false}, or an
     *     {@link AgentResult} when {@code wait=true}
     */
    public Object runNow(String name, boolean wait) {
        if (!wait) {
            return runNow(name);
        }
        return runNowAndWait(name);
    }

    /**
     * Fetch the schedule by its wire {@code name}, start it, then poll until the
     * triggered workflow reaches a terminal state and return it as an
     * {@link AgentResult}.
     *
     * @throws ScheduleException.Timeout if the workflow has not finished within the timeout
     */
    public AgentResult runNowAndWait(String name) {
        return runNowAndWait(name, DEFAULT_WAIT_TIMEOUT_MS, DEFAULT_POLL_INTERVAL_MS);
    }

    /**
     * Fetch the schedule by its wire {@code name}, start it, then poll until the
     * triggered workflow reaches a terminal state and return it as an
     * {@link AgentResult}.
     *
     * <p>The completed {@link Workflow} is converted via the SDK's shared
     * workflow → {@link AgentResult} extraction ({@link AgentHandle#fromWorkflow})
     * — the same logic the {@code AgentHandle.waitForResult} path uses — so the
     * output, status, error, token usage, and tool calls match a direct run.
     *
     * @param name           the schedule's wire name
     * @param timeoutMs      maximum time to wait, in milliseconds
     * @param pollIntervalMs delay between status polls, in milliseconds
     * @throws ScheduleException.Timeout if the workflow has not finished within {@code timeoutMs}
     */
    public AgentResult runNowAndWait(String name, long timeoutMs, long pollIntervalMs) {
        String executionId = runNow(name);
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (true) {
            Workflow wf = workflowClient.getWorkflow(executionId, true);
            if (isTerminal(wf)) {
                return AgentHandle.fromWorkflow(wf);
            }
            if (System.currentTimeMillis() >= deadline) {
                throw new ScheduleException.Timeout("runNow('" + name + "') did not finish within " + timeoutMs + "ms");
            }
            if (pollIntervalMs > 0) {
                try {
                    Thread.sleep(pollIntervalMs);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new ScheduleException.Timeout("runNow('" + name + "') was interrupted while waiting");
                }
            }
        }
    }

    /** {@code true} if the workflow has reached a terminal state (completed/failed/terminated/timed-out). */
    static boolean isTerminal(Workflow wf) {
        Workflow.WorkflowStatus status = wf != null ? wf.getStatus() : null;
        return status != null && status.isTerminal();
    }

    public List<Long> previewNext(String cron, int n) {
        List<Long> resp = exec(
                ConductorClientRequest.builder()
                        .method(Method.GET)
                        .path("/scheduler/nextFewSchedules")
                        .addQueryParam("cronExpression", cron)
                        .addQueryParam("limit", Integer.valueOf(n))
                        .build(),
                LIST_LONG_TYPE);
        return resp != null ? resp : new ArrayList<>();
    }

    // ── Declarative reconcile ───────────────────────────────────────────

    /**
     * Apply declarative scheduling semantics:
     * <ul>
     *   <li>{@code null} → no-op</li>
     *   <li>empty list → purge all schedules whose workflow == agent</li>
     *   <li>non-empty list → upsert listed, delete any other schedule for this agent</li>
     * </ul>
     */
    public void reconcile(String agentName, List<Schedule> desired) {
        if (desired == null) return;
        checkUniqueNames(desired);

        Map<String, String> existingWireByShort = new LinkedHashMap<>();
        for (ScheduleInfo info : list(agentName)) {
            existingWireByShort.put(info.getShortName(), info.getName());
        }
        Set<String> desiredShort = new HashSet<>();
        for (Schedule s : desired) desiredShort.add(s.getName());

        for (Map.Entry<String, String> entry : existingWireByShort.entrySet()) {
            if (!desiredShort.contains(entry.getKey())) {
                delete(entry.getValue());
            }
        }
        for (Schedule s : desired) {
            save(s, agentName);
        }
    }

    // ── Internals ───────────────────────────────────────────────────────

    static String prefix(String agentName, String shortName) {
        return agentName + "-" + shortName;
    }

    static String unprefix(String agentName, String wireName) {
        String p = agentName + "-";
        return wireName.startsWith(p) ? wireName.substring(p.length()) : wireName;
    }

    static void checkUniqueNames(List<Schedule> schedules) {
        Set<String> seen = new HashSet<>();
        for (Schedule s : schedules) {
            if (!seen.add(s.getName())) {
                throw new ScheduleException.NameConflict(
                        "Duplicate schedule name '" + s.getName() + "' — names must be unique per agent");
            }
        }
    }

    static Map<String, Object> toSaveRequest(Schedule s, String agentName) {
        Map<String, Object> swr = new LinkedHashMap<>();
        swr.put("name", agentName);
        swr.put("input", s.getInput() == null ? new LinkedHashMap<>() : new LinkedHashMap<>(s.getInput()));

        Map<String, Object> req = new LinkedHashMap<>();
        req.put("name", prefix(agentName, s.getName()));
        req.put("cronExpression", s.getCron());
        req.put("zoneId", s.getTimezone());
        req.put("runCatchupScheduleInstances", s.isCatchup());
        req.put("paused", s.isPaused());
        if (s.getStartAt() != null) req.put("scheduleStartTime", s.getStartAt());
        if (s.getEndAt() != null) req.put("scheduleEndTime", s.getEndAt());
        if (s.getDescription() != null) req.put("description", s.getDescription());
        req.put("startWorkflowRequest", swr);
        return req;
    }

    @SuppressWarnings("unchecked")
    static ScheduleInfo fromWorkflowSchedule(Map<String, Object> ws, String agentHint) {
        Map<String, Object> swr = (Map<String, Object>) ws.getOrDefault("startWorkflowRequest", new HashMap<>());
        String wireName = (String) ws.getOrDefault("name", "");
        String swrName = (String) swr.getOrDefault("name", "");
        String agent = agentHint != null ? agentHint : (swrName.isEmpty() ? "" : swrName);

        return new ScheduleInfo(
                wireName,
                unprefix(agent, wireName),
                swrName,
                (String) ws.getOrDefault("cronExpression", ""),
                (String) ws.getOrDefault("zoneId", "UTC"),
                (Map<String, Object>) swr.getOrDefault("input", new HashMap<>()),
                Boolean.TRUE.equals(ws.get("paused")),
                (String) ws.get("pausedReason"),
                Boolean.TRUE.equals(ws.get("runCatchupScheduleInstances")),
                longOrNull(ws.get("scheduleStartTime")),
                longOrNull(ws.get("scheduleEndTime")),
                (String) ws.get("description"),
                longOrNull(ws.get("nextRunTime")),
                longOrNull(ws.get("createTime")),
                longOrNull(ws.get("updatedTime")),
                (String) ws.get("createdBy"),
                (String) ws.get("updatedBy"));
    }

    private static Long longOrNull(Object o) {
        return o instanceof Number ? ((Number) o).longValue() : null;
    }

    /** Execute a scheduler request returning a typed body via the native Conductor client. */
    private <T> T exec(ConductorClientRequest req, TypeReference<T> type) {
        try {
            return client.execute(req, type).getData();
        } catch (ConductorClientException e) {
            throw mapException(e);
        }
    }

    /** Execute a scheduler request that returns no body. */
    private void execVoid(ConductorClientRequest req) {
        try {
            client.execute(req);
        } catch (ConductorClientException e) {
            throw mapException(e);
        }
    }

    /** Map Conductor's exception to the scheduler's typed exceptions (preserves the contract). */
    private static RuntimeException mapException(ConductorClientException e) {
        int status = e.getStatus();
        String msg = e.getMessage() != null ? e.getMessage() : "";
        if (status == 404) return new ScheduleException.NotFound(msg);
        if (status == 400 && msg.toLowerCase().contains("cron")) {
            return new ScheduleException.InvalidCron(msg);
        }
        return new AgentAPIException(status, msg);
    }
}
