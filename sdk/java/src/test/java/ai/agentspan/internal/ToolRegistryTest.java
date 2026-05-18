// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import ai.agentspan.annotations.Tool;
import ai.agentspan.model.ToolDef;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for {@link ToolRegistry}.
 */
class ToolRegistryTest {

    // Date / time (JSR-310) — needs JavaTimeModule on the internal JsonMapper.

    public static class TimeTools {
        static final AtomicReference<Object> seen = new AtomicReference<>();
        @Tool(name = "take_local_date", description = "x") public String takeLocalDate(LocalDate v) { seen.set(v); return "ok"; }
        @Tool(name = "take_instant",    description = "x") public String takeInstant(Instant v)     { seen.set(v); return "ok"; }
        @Tool(name = "take_duration",   description = "x") public String takeDuration(Duration v)   { seen.set(v); return "ok"; }
    }

    @Test
    void local_date_received_as_local_date() {
        TimeTools tools = new TimeTools();
        invokeSingleArg(tools, "take_local_date", "v", "2026-05-12");
        assertInstanceOf(LocalDate.class, TimeTools.seen.get(),
            "LocalDate parameter c as " + TimeTools.seen.get().getClass());
    }

    @Test
    void instant_received_as_instant() {
        TimeTools tools = new TimeTools();
        invokeSingleArg(tools, "take_instant", "v", "2026-05-12T13:45:00Z");
        assertInstanceOf(Instant.class, TimeTools.seen.get(),
            "Instant parameter received as " + TimeTools.seen.get().getClass());
    }

    @Test
    void duration_received_as_duration() {
        TimeTools tools = new TimeTools();
        invokeSingleArg(tools, "take_duration", "v", "PT5M");
        assertInstanceOf(Duration.class, TimeTools.seen.get(),
            "Duration parameter received as " + TimeTools.seen.get().getClass());
    }

    // Optional — needs Jdk8Module.

    public static class OptionalTools {
        static final AtomicReference<Object> seen = new AtomicReference<>();
        @Tool(name = "take_optional_string", description = "x")
        public String takeOptionalString(Optional<String> v) { seen.set(v); return "ok"; }
    }

    @Test
    void optional_string_received_as_optional() {
        OptionalTools tools = new OptionalTools();
        invokeSingleArg(tools, "take_optional_string", "v", "hello");
        assertInstanceOf(Optional.class, OptionalTools.seen.get(),
            "Optional parameter received as " + OptionalTools.seen.get().getClass());
    }

    // List<LocalDate>

    public static class ListTools {
        static final AtomicReference<Object> seen = new AtomicReference<>();
        @Tool(name = "take_list_localdate", description = "x")
        public String takeListLocalDate(List<LocalDate> v) { seen.set(v); return "ok"; }
    }

    @Test
    void list_of_local_date_elements_are_local_dates() {
        ListTools tools = new ListTools();
        invokeSingleArg(tools, "take_list_localdate", "v", Arrays.asList("2026-05-12", "2026-05-13"));
        Object got = ListTools.seen.get();
        assertInstanceOf(List.class, got);
        List<?> list = (List<?>) got;
        assertFalse(list.isEmpty());
        assertInstanceOf(LocalDate.class, list.get(0),
            "List<LocalDate> elements arrived as " + list.get(0).getClass());
    }

    // Schemas — what the LLM sees.

    @Test
    void schema_for_local_date_should_be_string_format_date() {
        Map<String, Object> schema = ToolRegistry.typeToJsonSchema(LocalDate.class);
        assertEquals("string", schema.get("type"),
            "LocalDate schema is " + schema + " — LLM has no idea it must emit an ISO-8601 date");
        assertEquals("date", schema.get("format"),
            "LocalDate schema should declare format=date");
    }

    private static <T> T invokeSingleArg(Object toolsInstance, String toolName,
                                          String paramName, Object rawValue) {
        List<ToolDef> defs = ToolRegistry.fromInstance(toolsInstance);
        ToolDef def = defs.stream()
            .filter(d -> d.getName().equals(toolName))
            .findFirst()
            .orElseThrow(() -> new AssertionError("tool not found: " + toolName));

        Map<String, Object> input = new LinkedHashMap<>();
        input.put(paramName, rawValue);

        Object result = def.getFunc().apply(input);
        @SuppressWarnings("unchecked")
        T cast = (T) result;
        return cast;
    }
}
