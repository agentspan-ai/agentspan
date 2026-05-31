/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.TextNode;

/**
 * Redacts secret values from execution-read response payloads.
 *
 * <p>Given an execution id + user id, looks up which secret names were disclosed
 * to workers for that execution (via {@link SecretDisclosureService}), fetches
 * each value's current plaintext from the store, and replaces every occurrence
 * of that plaintext with {@code ***NAME***}.</p>
 *
 * <p>The masker is invoked on JSON-serialized payloads from
 * {@link dev.agentspan.runtime.controller.SecretMaskingResponseAdvice}. A naive
 * {@code String.replace} on the JSON string misses secrets whose raw bytes
 * differ from their JSON encoding — e.g. a PEM key whose raw form contains
 * literal {@code 0x0A} bytes but whose JSON form contains the 2-char escape
 * {@code \n}, or a value containing a {@code "} that becomes {@code \"}. So
 * the masker parses the payload as a tree, walks every string node, and runs
 * literal-string replacement against the unescaped text-node value. Jackson
 * re-encodes correctly on serialization.</p>
 *
 * <p>If the payload isn't valid JSON the masker falls back to literal
 * string-replace, preserving the older contract for any non-JSON caller.</p>
 *
 * <p>Conservative threshold: secret values shorter than 8 characters are not
 * masked. Short values produce too many false positives in natural-language
 * output.</p>
 *
 * <p>If a disclosed secret has since been rotated or deleted, its old value
 * obviously won't match the current store value. This is acceptable: rotation
 * implies the old value is no longer a live credential.</p>
 */
@Service
public class SecretOutputMasker {

    private static final int MIN_MASK_LENGTH = 8;

    private final SecretStoreProvider store;
    private final SecretDisclosureService disclosures;
    private final ObjectMapper mapper = new ObjectMapper();

    public SecretOutputMasker(SecretStoreProvider store, SecretDisclosureService disclosures) {
        this.store = store;
        this.disclosures = disclosures;
    }

    /**
     * Return {@code payload} with all disclosed secret values for this execution
     * replaced by {@code ***NAME***}. Returns the payload unchanged if there are
     * no disclosures, the payload is null/empty, or no values match.
     */
    public String mask(String executionId, String userId, String payload) {
        if (payload == null || payload.isEmpty()) return payload;

        List<String> names = disclosures.namesFor(executionId, userId);
        if (names.isEmpty()) return payload;

        // Resolve disclosed names → current plaintext values once. Skip
        // rotated/deleted (null) and too-short values.
        List<Map.Entry<String, String>> pairs = new ArrayList<>();
        for (String name : names) {
            String value = store.get(userId, name);
            if (value == null || value.length() < MIN_MASK_LENGTH) continue;
            pairs.add(Map.entry(name, value));
        }
        if (pairs.isEmpty()) return payload;

        // Tree-walk path: parse the JSON, mask every text node, re-serialize.
        // Falls back to literal-string replacement if the payload isn't JSON
        // (preserves the older contract for any plain-text caller).
        try {
            JsonNode root = mapper.readTree(payload);
            walkAndMask(root, pairs);
            return mapper.writeValueAsString(root);
        } catch (Exception jsonParseFailed) {
            String redacted = payload;
            for (Map.Entry<String, String> pair : pairs) {
                redacted = redacted.replace(pair.getValue(), "***" + pair.getKey() + "***");
            }
            return redacted;
        }
    }

    /** Recursively mask string-valued nodes; field names are never touched. */
    private void walkAndMask(JsonNode node, List<Map.Entry<String, String>> pairs) {
        if (node instanceof ObjectNode obj) {
            Iterator<String> fields = obj.fieldNames();
            // Collect field names first to avoid ConcurrentModificationException
            // when we replace child nodes during iteration.
            List<String> fieldList = new ArrayList<>();
            while (fields.hasNext()) fieldList.add(fields.next());

            for (String field : fieldList) {
                JsonNode child = obj.get(field);
                if (child.isTextual()) {
                    String masked = maskString(child.asText(), pairs);
                    if (masked != null) obj.set(field, TextNode.valueOf(masked));
                } else if (child.isContainerNode()) {
                    walkAndMask(child, pairs);
                }
            }
        } else if (node instanceof ArrayNode arr) {
            for (int i = 0; i < arr.size(); i++) {
                JsonNode child = arr.get(i);
                if (child.isTextual()) {
                    String masked = maskString(child.asText(), pairs);
                    if (masked != null) arr.set(i, TextNode.valueOf(masked));
                } else if (child.isContainerNode()) {
                    walkAndMask(child, pairs);
                }
            }
        }
        // Other scalar nodes (numbers, booleans, nulls) can't contain secrets.
    }

    /** Returns the masked text or {@code null} if nothing was replaced (fast path). */
    private String maskString(String text, List<Map.Entry<String, String>> pairs) {
        if (text == null || text.isEmpty()) return null;
        String out = text;
        boolean changed = false;
        for (Map.Entry<String, String> pair : pairs) {
            String value = pair.getValue();
            if (out.contains(value)) {
                out = out.replace(value, "***" + pair.getKey() + "***");
                changed = true;
            }
        }
        return changed ? out : null;
    }
}
