/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.util;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class SchemaSubsetValidatorTest {

    @Test
    void acceptsAllSupportedKeywordsAtTopLevel() {
        // The exhaustive supported-keyword set, packed into a single schema
        // so a future addition to SUPPORTED that's not actually wired into
        // schemaValidatorScript trips an obvious tripwire (the test author
        // who added the keyword reads this list and asks themselves
        // "did I implement the runtime side too?").
        Map<String, Object> schema = Map.of(
                "type",
                "object",
                "properties",
                Map.of("name", Map.of("type", "string", "minLength", 1, "pattern", "^[A-Z]")),
                "required",
                List.of("name"),
                "additionalProperties",
                false,
                "enum",
                List.of("a", "b"),
                "minimum",
                0,
                "maximum",
                10,
                "description",
                "human-readable",
                "title",
                "X");
        SchemaSubsetValidator.validate(schema, "test");
    }

    @Test
    void nullOrEmptySchemaIsNoOp() {
        // Mirrors the runtime path which early-returns on null/empty —
        // PAC compile must not break legacy callers that don't declare
        // an inputSchema.
        SchemaSubsetValidator.validate(null, "test");
        SchemaSubsetValidator.validate(Map.of(), "test");
    }

    @Test
    void rejectsRef() {
        // The headline case. $ref looks like it works (Draft-07 standard)
        // but the runtime walks past it without dereferencing — silent
        // permissive validation.
        Map<String, Object> schema = Map.of("$ref", "#/definitions/Foo");
        assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "tool 'x' inputSchema"))
                .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                .hasMessageContaining("$ref")
                .hasMessageContaining("tool 'x' inputSchema")
                .hasMessageContaining("Draft-07 subset");
    }

    @Test
    void rejectsCombinatorKeywords() {
        for (String kw : List.of("allOf", "anyOf", "oneOf", "not")) {
            Map<String, Object> schema = Map.of(kw, List.of(Map.of("type", "string")));
            assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "x"))
                    .as("must reject %s", kw)
                    .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                    .hasMessageContaining(kw);
        }
    }

    @Test
    void rejectsConditionalKeywords() {
        for (String kw : List.of("if", "then", "else")) {
            Map<String, Object> schema = Map.of(kw, Map.of("type", "string"));
            assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "x"))
                    .as("must reject %s", kw)
                    .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                    .hasMessageContaining(kw);
        }
    }

    @Test
    void rejectsFormatKeyword() {
        // ``format`` is the most-likely-to-be-misused case — users write
        // ``"format": "email"`` and assume the runtime enforces email
        // syntax. It doesn't.
        Map<String, Object> schema = Map.of("type", "string", "format", "email");
        assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "x"))
                .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                .hasMessageContaining("format");
    }

    @Test
    void rejectsTypoedUnknownKeyword() {
        // ``minimumm`` (typo) — neither supported nor known-unsupported.
        // Reject as unknown so the user notices the typo at compile time.
        Map<String, Object> schema = Map.of("type", "number", "minimumm", 0);
        assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "x"))
                .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                .hasMessageContaining("unknown JSON Schema keyword 'minimumm'");
    }

    @Test
    void rejectsNestedUnsupportedInProperties() {
        // The nested-property case is the most insidious — top-level
        // schema looks clean but a property uses $ref. Path must point
        // at the property.
        Map<String, Object> schema =
                Map.of("type", "object", "properties", Map.of("user", Map.of("$ref", "#/definitions/User")));
        assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "tool 'x' inputSchema"))
                .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                .hasMessageContaining("$ref")
                .hasMessageContaining("/properties/user");
    }

    @Test
    void rejectsNestedUnsupportedInItems() {
        Map<String, Object> schema =
                Map.of("type", "array", "items", Map.of("oneOf", List.of(Map.of("type", "string"))));
        assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "tool 'x' inputSchema"))
                .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                .hasMessageContaining("oneOf")
                .hasMessageContaining("/items");
    }

    @Test
    void rejectsTupleFormItemsArrayElement() {
        // Draft-04/06 tuple-form items as an array. The runtime doesn't
        // handle this either — and a tuple element using oneOf must still
        // be caught, recursing through the list.
        Map<String, Object> schema =
                Map.of("type", "array", "items", List.of(Map.of("type", "string"), Map.of("$ref", "#/x")));
        assertThatThrownBy(() -> SchemaSubsetValidator.validate(schema, "x"))
                .isInstanceOf(SchemaSubsetValidator.UnsupportedSchemaException.class)
                .hasMessageContaining("$ref")
                .hasMessageContaining("/items[1]");
    }
}
