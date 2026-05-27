// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Java mirror of the Python {@code test_planner_context.py} / TS
 * {@code planner-context.test.ts} Context-class tests. Pins the wire
 * shape so the four SDKs stay in lock-step.
 */
class ContextTest {

    @Test
    void rejectsNeitherTextNorUrl() {
        IllegalArgumentException e = assertThrows(
            IllegalArgumentException.class,
            () -> Context.builder().build()
        );
        assertTrue(
            e.getMessage().contains("exactly one of text or url"),
            "message was: " + e.getMessage()
        );
    }

    @Test
    void rejectsBothTextAndUrl() {
        IllegalArgumentException e = assertThrows(
            IllegalArgumentException.class,
            () -> Context.builder().text("x").url("https://y/").build()
        );
        assertTrue(e.getMessage().contains("exactly one of text or url"));
    }

    @Test
    void textShorthandConstruction() {
        Context c = Context.text("rule one");
        assertEquals("rule one", c.getText());
        assertEquals(null, c.getUrl());
    }

    @Test
    void urlShorthandHasDefaults() {
        Context c = Context.url("https://x/y");
        assertEquals("https://x/y", c.getUrl());
        assertEquals(null, c.getText());
        assertTrue(c.isRequired(), "required defaults to true");
        assertEquals(16384, c.getMaxBytes());
    }

    @Test
    void toJsonTextOnlyIsMinimal() {
        // Text-only entries serialise as a single-key map — no url, headers,
        // required, maxBytes. Keeps the wire payload tight for the common
        // inline-rules case.
        assertEquals(Map.of("text", "rule"), Context.text("rule").toJson());
    }

    @Test
    void toJsonUrlOnlyWithDefaultsIsMinimal() {
        // URL with all defaults: only url on the wire (server applies the
        // same defaults). Mirrors Python/TS to_dict/toJSON behaviour.
        assertEquals(Map.of("url", "https://x/"), Context.url("https://x/").toJson());
    }

    @Test
    void toJsonUrlFullOptionsPreservesCredentialPlaceholder() {
        // Credential placeholder MUST pass through verbatim — the ${} -> #{}
        // escape is the server's job. SDKs must not pre-escape; otherwise
        // the credential resolver wouldn't see #{NAME} and resolution
        // would silently no-op.
        Context c = Context.builder()
                .url("https://confluence.example.com/page")
                .header("Authorization", "Bearer ${CONFLUENCE_TOKEN}")
                .required(false)
                .maxBytes(8192)
                .build();
        Map<String, Object> json = c.toJson();
        assertEquals("https://confluence.example.com/page", json.get("url"));
        assertEquals(Map.of("Authorization", "Bearer ${CONFLUENCE_TOKEN}"), json.get("headers"));
        assertEquals(false, json.get("required"));
        assertEquals(8192, json.get("maxBytes"));
    }

    @Test
    void varargsShorthandOnBuilderHelper() {
        // Builder.plannerContext(String...) on Agent (tested separately)
        // wraps each string in Context.text. Smoke-test the underlying
        // Context.text shorthand we depend on.
        Context a = Context.text("a");
        Context b = Context.text("b");
        assertEquals(List.of("a", "b"), List.of(a.getText(), b.getText()));
    }
}
