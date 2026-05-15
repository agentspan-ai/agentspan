// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.AgentStatus;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 13: Tool argument types — end-to-end coverage of the
 * server-task → SDK-coerce → method-invoke pipeline for {@code java.time}
 * types in {@code @Tool} signatures.
 *
 * <p>Each test prompts the agent to call a tool with a known value and
 * captures the argument the method body actually received via an
 * {@link AtomicReference}. Assertions check that the runtime type matches the
 * declared parameter type, not the raw string the server emitted.
 *
 * <p>Per CLAUDE.md: no LLM output text is inspected for correctness. The
 * side-effect (recorded argument) is the strongest signal — if coercion
 * regresses the captured value will be the wrong type and the test fails.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite18ToolTypes extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    public static class TypeTools {
        static final AtomicReference<Object> seenLocalDate = new AtomicReference<>();
        static final AtomicReference<Object> seenInstant   = new AtomicReference<>();
        static final AtomicReference<Object> seenListDate  = new AtomicReference<>();

        @Tool(name = "record_item_date",
              description = "Record a single date. Pass an ISO-8601 calendar date (e.g. 2026-05-12).")
        public String recordItemDate(LocalDate date) {
            seenLocalDate.set(date);
            return "recorded";
        }

        @Tool(name = "record_event_time",
              description = "Record an event timestamp. Pass an ISO-8601 instant (e.g. 2026-05-12T13:45:00Z).")
        public String recordEventTime(Instant when) {
            seenInstant.set(when);
            return "recorded";
        }

        @Tool(name = "record_item_dates",
              description = "Record a list of dates. Pass an array of ISO-8601 calendar dates.")
        public String recordItemDates(List<LocalDate> dates) {
            seenListDate.set(dates);
            return "recorded";
        }
    }

    private AgentResult runWith(String agentName, String prompt) {
        TypeTools tools = new TypeTools();
        Agent agent = Agent.builder()
            .name(agentName)
            .model(MODEL)
            .instructions("You must call the specified tool with the values from the user message exactly as given. "
                + "Do not answer in plain text. Do not invent values. Call exactly one tool, then stop.")
            .tools(ToolRegistry.fromInstance(tools))
            .maxTurns(3)
            .build();
        return runtime.run(agent, prompt);
    }

    @Test
    @Order(1)
    void test_local_date_is_local_date() {
        TypeTools.seenLocalDate.set(null);
        AgentResult result = runWith("e2e_java_types_localdate",
            "Call record_item_date with date=2026-05-12.");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "agent did not complete. error=" + result.getError());
        Object seen = TypeTools.seenLocalDate.get();
        assertNotNull(seen, "tool reported called but seen reference is null — race or coercion swallow");
        assertInstanceOf(LocalDate.class, seen,
            "LocalDate parameter received as " + seen.getClass());
        assertEquals(LocalDate.of(2026, 5, 12), seen);
    }

    @Test
    @Order(2)
    void test_instant_is_instant() {
        TypeTools.seenInstant.set(null);
        AgentResult result = runWith("e2e_java_types_instant",
            "Call record_event_time with when=2026-05-12T13:45:00Z.");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "agent did not complete. error=" + result.getError());
        Object seen = TypeTools.seenInstant.get();
        assertNotNull(seen);
        assertInstanceOf(Instant.class, seen,
            "Instant parameter received as " + seen.getClass());
    }

    @Test
    @Order(3)
    void test_list_of_local_date_elements_are_local_dates() {
        TypeTools.seenListDate.set(null);
        AgentResult result = runWith("e2e_java_types_listdate",
            "Call record_item_dates with dates=[\"2026-05-12\", \"2026-05-13\"].");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "agent did not complete. error=" + result.getError());
        Object seen = TypeTools.seenListDate.get();
        assertNotNull(seen);
        assertInstanceOf(List.class, seen);
        List<?> list = (List<?>) seen;
        assertFalse(list.isEmpty(), "list is empty");
        assertInstanceOf(LocalDate.class, list.get(0),
            "List<LocalDate> elements arrived as " + list.get(0).getClass());
    }

}
