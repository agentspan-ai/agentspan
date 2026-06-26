/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.spi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Behavioral contract every {@link SecretOutputMasker} implementation must satisfy.
 *
 * <p>The redaction <em>algorithm</em> (per-execution disclosure lookup, Jackson tree-walk,
 * JSON-escape handling) lives in the enterprise module, not in OSS — so this is an
 * <strong>abstract</strong> contract, not a runnable test on its own. The enterprise module
 * extends it (wiring its real masker + disclosure store via {@link #masker()} and
 * {@link #disclose}) so the same spec runs against the production implementation. The
 * standalone server's {@code NoOpSecretOutputMasker} intentionally does <em>not</em> extend
 * this — it has no disclosure tracking and would (correctly) fail the redaction cases.</p>
 *
 * <p>OSS keeps {@code ReferenceSecretOutputMaskerContractTest} as the conformance check that
 * this spec passes against a correct redactor and is therefore meaningful (it can fail).</p>
 *
 * <p><b>Reuse:</b> to run from the enterprise module, this class must be on its test classpath —
 * publish {@code conductor-agentspan-server} test sources as a Maven test-jar (the same
 * cross-module reuse mechanism the e2e "Option C" container uses for the SDK suite).</p>
 */
public abstract class SecretOutputMaskerContract {

    protected static final String EXEC = "exec-contract-1";
    protected static final String USER = "user-contract-1";

    protected final ObjectMapper mapper = new ObjectMapper();

    /** The implementation under test. */
    protected abstract SecretOutputMasker masker();

    /**
     * Record that {@code value} (under credential {@code name}) was disclosed during
     * {@code (executionId, userId)}, so a subsequent {@code mask} for that scope must redact it.
     */
    protected abstract void disclose(String executionId, String userId, String name, String value);

    // ── Contract ────────────────────────────────────────────────────────

    @Test
    void noDisclosures_returnsPayloadSemanticallyUnchanged() throws Exception {
        String payload = mapper.writeValueAsString(Map.of("output", "nothing secret here"));

        String masked = masker().mask(EXEC, USER, payload);

        // No disclosures for this scope ⇒ content is preserved (allow reformatting).
        assertThat(mapper.readTree(masked)).isEqualTo(mapper.readTree(payload));
    }

    @Test
    void disclosedPlaintext_isRedacted() throws Exception {
        String secret = "ghp_supersecretvalue123";
        disclose(EXEC, USER, "GH_TOKEN", secret);
        String payload = mapper.writeValueAsString(Map.of("output", "the token is " + secret));

        String masked = masker().mask(EXEC, USER, payload);

        assertThat(masked).doesNotContain(secret);
        assertThat(mapper.readTree(masked).get("output").asText())
                .contains("***GH_TOKEN***")
                .doesNotContain(secret);
    }

    @Test
    void valueWithJsonSpecialChars_isRedacted() throws Exception {
        // A secret containing a quote and a newline: in the JSON wire form these are escaped,
        // so a naive String.replace over the raw JSON would miss it. A correct impl walks the
        // parsed tree and operates on the decoded string node.
        String secret = "line1\n\"quoted\"\tline2";
        disclose(EXEC, USER, "MULTILINE", secret);
        String payload = mapper.writeValueAsString(Map.of("output", "prefix-" + secret + "-suffix"));

        String masked = masker().mask(EXEC, USER, payload);

        String maskedValue = mapper.readTree(masked).get("output").asText();
        assertThat(maskedValue).contains("***MULTILINE***");
        assertThat(maskedValue).doesNotContain(secret);
    }

    @Test
    void redactsAcrossNestedStructures() throws Exception {
        String secret = "sk-deep-nested-secret";
        disclose(EXEC, USER, "NESTED", secret);
        String payload = mapper.writeValueAsString(Map.of(
                "tasks", java.util.List.of(
                        Map.of("name", "a", "out", "value=" + secret),
                        Map.of("name", "b", "out", "clean"))));

        String masked = masker().mask(EXEC, USER, payload);

        assertThat(masked).doesNotContain(secret);
        assertThat(masked).contains("***NESTED***");
    }

    @Test
    void scopedByExecution_otherExecutionNotRedacted() throws Exception {
        String secret = "scoped-to-exec-A-only";
        disclose("exec-A", USER, "SCOPED", secret);
        String payload = mapper.writeValueAsString(Map.of("output", "value=" + secret));

        // Masking a DIFFERENT execution must not redact exec-A's disclosure.
        String masked = masker().mask("exec-B", USER, payload);

        assertThat(masked).contains(secret);
    }

    @Test
    void malformedPayload_returnedUnchanged_neverThrows() {
        String notJson = "this is }{ not json";
        assertThatCode(() -> {
            String masked = masker().mask(EXEC, USER, notJson);
            assertThat(masked).isEqualTo(notJson);
        }).doesNotThrowAnyException();
    }
}
