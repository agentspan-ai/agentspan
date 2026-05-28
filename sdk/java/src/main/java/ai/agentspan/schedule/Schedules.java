// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.schedule;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import ai.agentspan.AgentConfig;
import ai.agentspan.exceptions.AgentAPIException;
import ai.agentspan.internal.JsonMapper;

/**
 * Lifecycle API for cron-based agent schedules. Obtained via {@code runtime.schedules()}.
 *
 * <p>Operations are keyed by the <strong>wire name</strong> (prefixed with
 * {@code agent-}) returned by {@link #list(String)}. Use {@link Schedule} to
 * construct the user-facing short name; the SDK prefixes it at deploy time.
 */
public class Schedules {

    private final AgentConfig config;
    private final HttpClient http;

    public Schedules(AgentConfig config, HttpClient http) {
        this.config = config;
        this.http = http;
    }

    // ── CRUD ────────────────────────────────────────────────────────────

    public void save(Schedule schedule, String agentName) {
        Map<String, Object> body = toSaveRequest(schedule, agentName);
        request("POST", "/api/scheduler/schedules", body);
    }

    @SuppressWarnings("unchecked")
    public ScheduleInfo get(String wireName) {
        Object resp = request("GET", "/api/scheduler/schedules/" + enc(wireName), null);
        if (!(resp instanceof Map) || ((Map<?, ?>) resp).isEmpty() || ((Map<?, ?>) resp).get("name") == null) {
            throw new ScheduleException.NotFound("Schedule '" + wireName + "' not found");
        }
        return fromWorkflowSchedule((Map<String, Object>) resp, null);
    }

    @SuppressWarnings("unchecked")
    public List<ScheduleInfo> list(String agentName) {
        Object resp = request(
                "GET", "/api/scheduler/schedules?workflowName=" + enc(agentName), null);
        if (!(resp instanceof List)) return new ArrayList<>();
        List<ScheduleInfo> out = new ArrayList<>();
        for (Object item : (List<Object>) resp) {
            if (item instanceof Map) {
                out.add(fromWorkflowSchedule((Map<String, Object>) item, agentName));
            }
        }
        return out;
    }

    public void pause(String wireName) { pause(wireName, null); }

    public void pause(String wireName, String reason) {
        String path = "/api/scheduler/schedules/" + enc(wireName) + "/pause";
        if (reason != null) path += "?reason=" + enc(reason);
        request("PUT", path, null);
    }

    public void resume(String wireName) {
        request("PUT", "/api/scheduler/schedules/" + enc(wireName) + "/resume", null);
    }

    public void delete(String wireName) {
        request("DELETE", "/api/scheduler/schedules/" + enc(wireName), null);
    }

    @SuppressWarnings("unchecked")
    public String runNow(ScheduleInfo info) {
        Object resp = request("POST", "/api/workflow/" + enc(info.getAgent()), info.getInput());
        if (resp instanceof String) return (String) resp;
        if (resp instanceof Map) return String.valueOf(((Map<String, Object>) resp).get("workflowId"));
        return String.valueOf(resp);
    }

    @SuppressWarnings("unchecked")
    public List<Long> previewNext(String cron, int n) {
        String path = "/api/scheduler/nextFewSchedules?cronExpression=" + enc(cron) + "&limit=" + n;
        Object resp = request("GET", path, null);
        if (!(resp instanceof List)) return new ArrayList<>();
        List<Long> out = new ArrayList<>();
        for (Object o : (List<Object>) resp) {
            if (o instanceof Number) out.add(((Number) o).longValue());
        }
        return out;
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

    private static String enc(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }

    /**
     * Issues an HTTP request and returns the parsed JSON body as a Map, List, String, or null.
     * Translates known status codes into typed schedule exceptions.
     */
    private Object request(String method, String path, Object body) {
        try {
            String url = config.getServerUrl() + path;
            String jsonBody = body == null ? null : JsonMapper.toJson(body);

            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json");
            addAuthHeaders(builder);

            switch (method) {
                case "GET": builder.GET(); break;
                case "DELETE": builder.DELETE(); break;
                case "POST":
                    builder.POST(jsonBody == null
                            ? HttpRequest.BodyPublishers.noBody()
                            : HttpRequest.BodyPublishers.ofString(jsonBody));
                    break;
                case "PUT":
                    builder.PUT(jsonBody == null
                            ? HttpRequest.BodyPublishers.noBody()
                            : HttpRequest.BodyPublishers.ofString(jsonBody));
                    break;
                default: throw new IllegalArgumentException("Unsupported method: " + method);
            }

            HttpResponse<String> response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            int status = response.statusCode();
            String text = response.body() == null ? "" : response.body();

            if (status >= 400) {
                if (status == 404) throw new ScheduleException.NotFound(text);
                if (status == 400 && text.toLowerCase().contains("cron")) {
                    throw new ScheduleException.InvalidCron(text);
                }
                throw new AgentAPIException(status, text);
            }

            if (text.isEmpty()) return null;
            String trimmed = text.trim();
            if (trimmed.startsWith("{")) return JsonMapper.fromJson(trimmed, Map.class);
            if (trimmed.startsWith("[")) return JsonMapper.fromJson(trimmed, List.class);
            // Bare workflow id or string
            return trimmed.replace("\"", "");
        } catch (ScheduleException | AgentAPIException e) {
            throw e;
        } catch (Exception e) {
            throw new ScheduleException("HTTP " + method + " " + path + " failed", e);
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
}
