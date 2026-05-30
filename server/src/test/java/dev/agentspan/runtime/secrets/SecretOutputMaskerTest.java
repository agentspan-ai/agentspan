/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.secrets;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class SecretOutputMaskerTest {

    private SecretStoreProvider store;
    private SecretDisclosureService disclosures;
    private SecretOutputMasker masker;

    private static final String USER = "u-mask";
    private static final String EXEC = "exec-mask-1";

    @BeforeEach
    void setUp() {
        store = mock(SecretStoreProvider.class);
        disclosures = mock(SecretDisclosureService.class);
        masker = new SecretOutputMasker(store, disclosures);
    }

    @Test
    void mask_replacesDisclosedValueInPayload() {
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("GITHUB_TOKEN"));
        when(store.get(USER, "GITHUB_TOKEN")).thenReturn("ghp_realtoken12345");

        String redacted = masker.mask(EXEC, USER, "error: token ghp_realtoken12345 expired");

        assertThat(redacted).isEqualTo("error: token ***GITHUB_TOKEN*** expired");
    }

    @Test
    void mask_replacesAllOccurrences() {
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("KEY"));
        when(store.get(USER, "KEY")).thenReturn("longsecretvalue99");

        String redacted = masker.mask(EXEC, USER, "first: longsecretvalue99 second: longsecretvalue99 done");

        assertThat(redacted).isEqualTo("first: ***KEY*** second: ***KEY*** done");
    }

    @Test
    void mask_handlesMultipleDisclosedSecrets() {
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("GITHUB_TOKEN", "OPENAI_API_KEY"));
        when(store.get(USER, "GITHUB_TOKEN")).thenReturn("ghp_realtoken12345");
        when(store.get(USER, "OPENAI_API_KEY")).thenReturn("sk-abcdefghijklmnopqrst");

        String out = masker.mask(EXEC, USER, "gh said ghp_realtoken12345, openai said sk-abcdefghijklmnopqrst");

        assertThat(out).isEqualTo("gh said ***GITHUB_TOKEN***, openai said ***OPENAI_API_KEY***");
    }

    @Test
    void mask_shortValuesNotMasked() {
        // 7 chars — below 8-char threshold; risk of false positives in natural text.
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("SHORT"));
        when(store.get(USER, "SHORT")).thenReturn("abc1234");

        String out = masker.mask(EXEC, USER, "the value is abc1234 here");

        assertThat(out).isEqualTo("the value is abc1234 here");
    }

    @Test
    void mask_unknownExecution_returnsPayloadUnchanged() {
        when(disclosures.namesFor("never-existed", USER)).thenReturn(List.of());

        String out = masker.mask("never-existed", USER, "anything goes here");

        assertThat(out).isEqualTo("anything goes here");
        verifyNoInteractions(store);
    }

    @Test
    void mask_nullOrEmptyPayload_returnsPayloadUnchanged() {
        assertThat(masker.mask(EXEC, USER, null)).isNull();
        assertThat(masker.mask(EXEC, USER, "")).isEmpty();
        verifyNoInteractions(disclosures, store);
    }

    @Test
    void mask_secretDeletedSinceDisclosure_silentlySkipped() {
        // Secret was rotated/deleted; store returns null. Don't crash; just skip.
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("ROTATED"));
        when(store.get(USER, "ROTATED")).thenReturn(null);

        String out = masker.mask(EXEC, USER, "payload with no match");

        assertThat(out).isEqualTo("payload with no match");
    }

    // ── Bug #2: masker called on JSON payloads — must understand JSON escaping ──

    @Test
    void mask_secretWithNewlines_masksWhenEmbeddedInJson() {
        // The masker is invoked by SecretMaskingResponseAdvice on a JSON-serialized
        // payload. If the secret value contains a newline (PEM key, multi-line
        // token), the raw value contains a 0x0A byte but the JSON payload has the
        // 2-char escape sequence \n. A literal String.replace() on the JSON
        // string will MISS the secret entirely and let it through. This test
        // proves the masker handles JSON-encoded payloads correctly.
        String secret = "-----BEGIN-----\nlinetwo\nlinethree\n-----END-----";
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("PEM"));
        when(store.get(USER, "PEM")).thenReturn(secret);

        // Simulate what the response advice sends in: JSON-serialized body that
        // contains the raw secret in one of its string fields.
        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        String json;
        try {
            json = mapper.writeValueAsString(java.util.Map.of("key", secret));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        // Sanity: JSON contains the *escaped* secret (\\n), not raw newlines.
        assertThat(json).contains("\\n");
        assertThat(json).doesNotContain("\n-----END-----");

        String redacted = masker.mask(EXEC, USER, json);

        // Critical: NO substring of the original raw secret may survive,
        // regardless of escaping. ***PEM*** placeholder must appear instead.
        assertThat(redacted).doesNotContain("-----BEGIN-----");
        assertThat(redacted).doesNotContain("linetwo");
        assertThat(redacted).contains("***PEM***");
    }

    @Test
    void mask_secretWithDoubleQuotes_masksWhenEmbeddedInJson() {
        // A secret containing a double-quote becomes \" in the JSON-serialized
        // payload. Literal-replace on the JSON string would miss it. After the
        // fix, the tree-walking masker reads the unescaped string from each
        // text node and masks it.
        String secret = "value-with-\"quoted\"-substring-1234567890";
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("Q"));
        when(store.get(USER, "Q")).thenReturn(secret);

        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        String json;
        try {
            json = mapper.writeValueAsString(java.util.Map.of("k", secret));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        // Sanity: JSON contains the escaped form.
        assertThat(json).contains("\\\"");

        String redacted = masker.mask(EXEC, USER, json);

        assertThat(redacted).doesNotContain("quoted");
        assertThat(redacted).contains("***Q***");
    }

    @Test
    void mask_specialRegexCharsInValue_treatedAsLiteral() {
        // Secret contains regex metacharacters — must use literal string replace,
        // not regex, or values like "a.b*c" would mask too aggressively.
        when(disclosures.namesFor(EXEC, USER)).thenReturn(List.of("REGEXY"));
        when(store.get(USER, "REGEXY")).thenReturn("a.b*c+d?e[f]");

        String out = masker.mask(EXEC, USER, "exact: a.b*c+d?e[f] also: aXbYcZdWe[f]");

        assertThat(out).isEqualTo("exact: ***REGEXY*** also: aXbYcZdWe[f]");
    }
}
