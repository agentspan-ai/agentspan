// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OpTest {

    @Test
    void rejectsNeitherArgsNorGenerate() {
        IllegalArgumentException e = assertThrows(
            IllegalArgumentException.class,
            () -> Op.builder("write_file").build()
        );
        assertTrue(
            e.getMessage().contains("exactly one of args or generate"),
            "message was: " + e.getMessage()
        );
    }

    @Test
    void rejectsBothArgsAndGenerate() {
        IllegalArgumentException e = assertThrows(
            IllegalArgumentException.class,
            () -> Op.builder("write_file")
                .args(Map.of("path", "x"))
                .generate(Generate.builder().instructions("i").outputSchema("{\"x\":1}").build())
                .build()
        );
        assertTrue(
            e.getMessage().contains("exactly one of args or generate"),
            "message was: " + e.getMessage()
        );
    }

    @Test
    void acceptsArgsOnly() {
        Op op = Op.builder("write_file").args(Map.of("path", "x")).build();
        Map<String, Object> j = op.toJson();
        assertEquals("write_file", j.get("tool"));
        assertNotNull(j.get("args"));
    }

    @Test
    void acceptsGenerateOnly() {
        Op op = Op.builder("write_file")
            .generate(Generate.builder().instructions("i").outputSchema("{\"x\":1}").build())
            .build();
        Map<String, Object> j = op.toJson();
        assertEquals("write_file", j.get("tool"));
        assertNotNull(j.get("generate"));
    }
}
