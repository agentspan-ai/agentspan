// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.schedule;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Unit tests for Schedule + Schedules helpers (no network). */
class ScheduleTest {

    // ── Schedule construction ─────────────────────────────────────────

    @Test
    void minimal() {
        Schedule s = Schedule.builder().name("daily").cron("0 0 9 * * ?").build();
        assertEquals("daily", s.getName());
        assertEquals("UTC", s.getTimezone());
        assertFalse(s.isCatchup());
        assertFalse(s.isPaused());
        assertTrue(s.getInput().isEmpty());
    }

    @Test
    void full() {
        Map<String, Object> input = new HashMap<>();
        input.put("c", "#eng");
        Schedule s = Schedule.builder()
                .name("w").cron("0 0 9 * * MON")
                .timezone("America/Los_Angeles")
                .input(input)
                .catchup(true).paused(true)
                .startAt(1000L).endAt(2000L)
                .description("desc")
                .build();
        assertEquals("America/Los_Angeles", s.getTimezone());
        assertEquals(input, s.getInput());
        assertTrue(s.isCatchup());
        assertTrue(s.isPaused());
        assertEquals(1000L, s.getStartAt());
        assertEquals(2000L, s.getEndAt());
    }

    @Test
    void rejectsEmptyName() {
        assertThrows(ScheduleException.class,
                () -> Schedule.builder().name("").cron("* * * * * ?").build());
        assertThrows(ScheduleException.class,
                () -> Schedule.builder().name("  ").cron("* * * * * ?").build());
    }

    @Test
    void rejectsEmptyCron() {
        assertThrows(ScheduleException.class,
                () -> Schedule.builder().name("x").cron("").build());
    }

    @Test
    void rejectsInvertedWindow() {
        assertThrows(ScheduleException.class,
                () -> Schedule.builder().name("x").cron("* * * * * ?").startAt(2000L).endAt(1000L).build());
        assertThrows(ScheduleException.class,
                () -> Schedule.builder().name("x").cron("* * * * * ?").startAt(1000L).endAt(1000L).build());
    }

    // ── Wire-name prefix/unprefix ─────────────────────────────────────

    @Test
    void prefixRoundtrips() {
        assertEquals("digest-daily", Schedules.prefix("digest", "daily"));
        assertEquals("daily", Schedules.unprefix("digest", "digest-daily"));
    }

    @Test
    void unprefixNoMatchReturnsInput() {
        assertEquals("unrelated", Schedules.unprefix("agent", "unrelated"));
    }

    @Test
    void agentNameWithHyphen() {
        String wire = Schedules.prefix("my-agent", "daily");
        assertEquals("my-agent-daily", wire);
        assertEquals("daily", Schedules.unprefix("my-agent", wire));
    }

    // ── Payload mapping ───────────────────────────────────────────────

    @Test
    void toSaveRequestMinimal() {
        Schedule s = Schedule.builder().name("daily").cron("0 0 9 * * ?").build();
        Map<String, Object> req = Schedules.toSaveRequest(s, "digest");
        assertEquals("digest-daily", req.get("name"));
        assertEquals("0 0 9 * * ?", req.get("cronExpression"));
        assertEquals("UTC", req.get("zoneId"));
        assertEquals(false, req.get("paused"));
        assertEquals(false, req.get("runCatchupScheduleInstances"));
        @SuppressWarnings("unchecked")
        Map<String, Object> swr = (Map<String, Object>) req.get("startWorkflowRequest");
        assertEquals("digest", swr.get("name"));
        assertTrue(((Map<?, ?>) swr.get("input")).isEmpty());
    }

    @Test
    void toSaveRequestFull() {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("c", "#eng"); input.put("n", 42);
        Schedule s = Schedule.builder()
                .name("w").cron("0 0 9 * * MON")
                .timezone("America/Los_Angeles")
                .input(input).catchup(true).paused(true)
                .startAt(1000L).endAt(2000L).description("desc")
                .build();
        Map<String, Object> req = Schedules.toSaveRequest(s, "digest");
        assertEquals("America/Los_Angeles", req.get("zoneId"));
        assertEquals(true, req.get("paused"));
        assertEquals(true, req.get("runCatchupScheduleInstances"));
        assertEquals(1000L, req.get("scheduleStartTime"));
        assertEquals(2000L, req.get("scheduleEndTime"));
        assertEquals("desc", req.get("description"));
    }

    @Test
    void inputCopiedNotShared() {
        Map<String, Object> original = new LinkedHashMap<>();
        original.put("a", 1);
        Schedule s = Schedule.builder().name("x").cron("* * * * * ?").input(original).build();
        Map<String, Object> req = Schedules.toSaveRequest(s, "agent");
        @SuppressWarnings("unchecked")
        Map<String, Object> swrInput = (Map<String, Object>) ((Map<String, Object>) req.get("startWorkflowRequest")).get("input");
        swrInput.put("mutated", true);
        assertNull(original.get("mutated"));
    }

    @Test
    void fromWorkflowScheduleBasic() {
        Map<String, Object> ws = new LinkedHashMap<>();
        ws.put("name", "digest-daily");
        ws.put("cronExpression", "0 0 9 * * ?");
        ws.put("zoneId", "UTC");
        ws.put("paused", false);
        Map<String, Object> swr = new LinkedHashMap<>();
        swr.put("name", "digest");
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("c", "#eng");
        swr.put("input", input);
        ws.put("startWorkflowRequest", swr);
        ws.put("createTime", 111L);
        ws.put("createdBy", "alice");

        ScheduleInfo info = Schedules.fromWorkflowSchedule(ws, "digest");
        assertEquals("digest-daily", info.getName());
        assertEquals("daily", info.getShortName());
        assertEquals("digest", info.getAgent());
        assertEquals("0 0 9 * * ?", info.getCron());
        assertFalse(info.isPaused());
        assertEquals(input, info.getInput());
        assertEquals(111L, info.getCreateTime());
        assertEquals("alice", info.getCreatedBy());
    }

    @Test
    void fromWorkflowScheduleDerivesAgentWhenOmitted() {
        Map<String, Object> ws = new LinkedHashMap<>();
        ws.put("name", "digest-daily");
        Map<String, Object> swr = new LinkedHashMap<>();
        swr.put("name", "digest");
        ws.put("startWorkflowRequest", swr);
        ScheduleInfo info = Schedules.fromWorkflowSchedule(ws, null);
        assertEquals("digest", info.getAgent());
        assertEquals("daily", info.getShortName());
    }

    // ── Unique-name validation ────────────────────────────────────────

    @Test
    void distinctNamesOk() {
        Schedules.checkUniqueNames(List.of(
                Schedule.builder().name("a").cron("* * * * * ?").build(),
                Schedule.builder().name("b").cron("* * * * * ?").build()
        ));
    }

    @Test
    void duplicateNameRaises() {
        assertThrows(ScheduleException.NameConflict.class, () -> Schedules.checkUniqueNames(List.of(
                Schedule.builder().name("a").cron("* * * * * ?").build(),
                Schedule.builder().name("a").cron("0 0 9 * * ?").build()
        )));
    }
}
