// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.schedule;

import ai.agentspan.AgentConfig;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Integration tests for the Java schedule SDK against the live agentspan-runtime.
 * Skipped if the scheduler endpoint isn't reachable.
 */
@EnabledIf("schedulerAvailable")
class ScheduleIntegrationTest {

    private static final String SERVER = System.getenv()
            .getOrDefault("AGENTSPAN_SERVER_URL", "http://localhost:6767");
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private static final String AGENT_NAME = "e2e_java_sched_noop_" +
            UUID.randomUUID().toString().substring(0, 8);

    private static Schedules schedules;

    static boolean schedulerAvailable() {
        try {
            HttpResponse<String> r = HTTP.send(
                    HttpRequest.newBuilder()
                            .uri(URI.create(SERVER + "/api/scheduler/schedules"))
                            .timeout(Duration.ofSeconds(3))
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            return r.statusCode() == 200;
        } catch (Exception e) {
            return false;
        }
    }

    @BeforeAll
    static void registerWorkflow() throws Exception {
        AgentConfig cfg = new AgentConfig(SERVER, null, null, 0, 0);
        schedules = new Schedules(cfg, HTTP);

        String body = "{\"name\":\"" + AGENT_NAME + "\",\"version\":1,\"schemaVersion\":2,"
                + "\"ownerEmail\":\"e2e@agentspan.test\",\"timeoutSeconds\":60,\"timeoutPolicy\":\"TIME_OUT_WF\","
                + "\"tasks\":[{\"name\":\"noop_terminate\",\"taskReferenceName\":\"noop_terminate_ref\","
                + "\"type\":\"TERMINATE\",\"inputParameters\":{\"terminationStatus\":\"COMPLETED\","
                + "\"workflowOutput\":{\"ok\":true}}}]}";

        HttpResponse<String> r = HTTP.send(
                HttpRequest.newBuilder()
                        .uri(URI.create(SERVER + "/api/metadata/workflow"))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
        if (r.statusCode() >= 400) {
            throw new RuntimeException("Workflow register failed: " + r.statusCode() + " " + r.body());
        }
    }

    @AfterAll
    static void unregisterWorkflow() throws Exception {
        if (schedules != null) {
            try { schedules.reconcile(AGENT_NAME, List.of()); } catch (Exception ignored) {}
        }
        HTTP.send(
                HttpRequest.newBuilder()
                        .uri(URI.create(SERVER + "/api/metadata/workflow/" + AGENT_NAME + "/1"))
                        .DELETE().build(),
                HttpResponse.BodyHandlers.ofString());
    }

    @AfterEach
    void clean() {
        try { schedules.reconcile(AGENT_NAME, List.of()); } catch (Exception ignored) {}
    }

    @Test
    void reconcileCreatesSchedules() {
        Map<String, Object> input = new HashMap<>();
        input.put("k", 1);
        schedules.reconcile(AGENT_NAME, List.of(
                Schedule.builder().name("daily").cron("0 0 9 * * ?").input(input).build(),
                Schedule.builder().name("weekly").cron("0 0 9 * * MON").build()
        ));
        List<ScheduleInfo> infos = schedules.list(AGENT_NAME);
        assertEquals(2, infos.size());

        ScheduleInfo daily = infos.stream().filter(i -> "daily".equals(i.getShortName())).findFirst().orElseThrow();
        assertEquals(AGENT_NAME + "-daily", daily.getName());
        assertEquals("0 0 9 * * ?", daily.getCron());
        assertEquals(input, daily.getInput());
        assertEquals(AGENT_NAME, daily.getAgent());
    }

    @Test
    void upsertAndPrune() {
        schedules.reconcile(AGENT_NAME, List.of(
                Schedule.builder().name("a").cron("0 0 1 * * ?").build(),
                Schedule.builder().name("b").cron("0 0 2 * * ?").build()
        ));
        schedules.reconcile(AGENT_NAME, List.of(
                Schedule.builder().name("a").cron("0 0 9 * * ?").build(),
                Schedule.builder().name("c").cron("0 0 17 * * ?").build()
        ));
        List<ScheduleInfo> infos = schedules.list(AGENT_NAME);
        assertEquals(2, infos.size());
        ScheduleInfo a = infos.stream().filter(i -> "a".equals(i.getShortName())).findFirst().orElseThrow();
        assertEquals("0 0 9 * * ?", a.getCron());
    }

    @Test
    void emptyListPurges() {
        schedules.reconcile(AGENT_NAME, List.of(Schedule.builder().name("x").cron("0 * * * * ?").build()));
        assertEquals(1, schedules.list(AGENT_NAME).size());
        schedules.reconcile(AGENT_NAME, List.of());
        assertTrue(schedules.list(AGENT_NAME).isEmpty());
    }

    @Test
    void nullPreserves() {
        schedules.reconcile(AGENT_NAME, List.of(Schedule.builder().name("x").cron("0 * * * * ?").build()));
        schedules.reconcile(AGENT_NAME, null);
        assertEquals(1, schedules.list(AGENT_NAME).size());
    }

    @Test
    void duplicateNameRaises() {
        assertThrows(ScheduleException.NameConflict.class, () -> schedules.reconcile(AGENT_NAME, List.of(
                Schedule.builder().name("dup").cron("0 * * * * ?").build(),
                Schedule.builder().name("dup").cron("0 0 9 * * ?").build()
        )));
        assertTrue(schedules.list(AGENT_NAME).isEmpty());
    }

    @Test
    void pauseResume() {
        schedules.reconcile(AGENT_NAME, List.of(Schedule.builder().name("p").cron("0 0 9 * * ?").build()));
        String wire = AGENT_NAME + "-p";
        assertFalse(schedules.get(wire).isPaused());
        schedules.pause(wire, "rate limit");
        assertTrue(schedules.get(wire).isPaused());
        schedules.resume(wire);
        assertFalse(schedules.get(wire).isPaused());
    }

    @Test
    void pausedOnCreatePreservesState() {
        schedules.reconcile(AGENT_NAME, List.of(
                Schedule.builder().name("silent").cron("0 0 9 * * ?").paused(true).build()));
        assertTrue(schedules.get(AGENT_NAME + "-silent").isPaused());
    }

    @Test
    void deleteRemoves() {
        schedules.reconcile(AGENT_NAME, List.of(Schedule.builder().name("d").cron("0 * * * * ?").build()));
        schedules.delete(AGENT_NAME + "-d");
        assertTrue(schedules.list(AGENT_NAME).isEmpty());
    }

    @Test
    void getAfterDeleteRaises() {
        schedules.reconcile(AGENT_NAME, List.of(Schedule.builder().name("g").cron("0 * * * * ?").build()));
        String wire = AGENT_NAME + "-g";
        schedules.delete(wire);
        assertThrows(ScheduleException.NotFound.class, () -> schedules.get(wire));
    }

    @Test
    void previewNext() {
        List<Long> times = schedules.previewNext("0 0 9 * * ?", 3);
        assertEquals(3, times.size());
        for (int i = 1; i < times.size(); i++) {
            assertTrue(times.get(i) > times.get(i - 1));
        }
    }
}
