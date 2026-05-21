/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.ai.retry.NonTransientAiException;

/**
 * Unit tests for {@link AuthErrorMessageMapper}.
 *
 * <p>The mapper recognises authentication failures from upstream LLM providers
 * (typically surfaced by Spring AI as {@link NonTransientAiException} or via
 * HTTP client errors carrying "401" / "Unauthorized" / "invalid_api_key" in
 * the message) and produces a clear, actionable error message naming the
 * provider, env var, and remediation paths.</p>
 */
class AuthErrorMessageMapperTest {

    @Test
    void detects401InTopLevelException() {
        Throwable t = new NonTransientAiException(
                "HTTP 401 Unauthorized: Invalid x-api-key");
        assertThat(AuthErrorMessageMapper.isAuthFailure(t)).isTrue();
    }

    @Test
    void detectsUnauthorizedInMessage() {
        Throwable t = new RuntimeException("Unauthorized: bad token");
        assertThat(AuthErrorMessageMapper.isAuthFailure(t)).isTrue();
    }

    @Test
    void detectsInvalidApiKeyInMessage() {
        Throwable t = new RuntimeException("error code: invalid_api_key");
        assertThat(AuthErrorMessageMapper.isAuthFailure(t)).isTrue();
    }

    @Test
    void traversesCauseChain() {
        Throwable root = new NonTransientAiException("401 Unauthorized");
        Throwable mid = new RuntimeException("downstream failed", root);
        Throwable top = new RuntimeException("workflow task failed", mid);
        assertThat(AuthErrorMessageMapper.isAuthFailure(top)).isTrue();
    }

    @Test
    void ignoresRateLimitErrors() {
        Throwable t = new NonTransientAiException("HTTP 429 Too Many Requests");
        assertThat(AuthErrorMessageMapper.isAuthFailure(t)).isFalse();
    }

    @Test
    void ignoresServerErrors() {
        Throwable t = new RuntimeException("HTTP 500 Internal Server Error");
        assertThat(AuthErrorMessageMapper.isAuthFailure(t)).isFalse();
    }

    @Test
    void ignoresTimeoutErrors() {
        Throwable t = new RuntimeException("Read timeout after 30s");
        assertThat(AuthErrorMessageMapper.isAuthFailure(t)).isFalse();
    }

    @Test
    void ignoresNullThrowable() {
        assertThat(AuthErrorMessageMapper.isAuthFailure(null)).isFalse();
    }

    @Test
    void messageNamesProviderAndEnvVar() {
        String msg = AuthErrorMessageMapper.buildMessage("anthropic", "ANTHROPIC_API_KEY");
        assertThat(msg)
                .contains("anthropic")
                .contains("ANTHROPIC_API_KEY")
                .contains("PUT /api/credentials/ANTHROPIC_API_KEY");
    }

    @Test
    void messageMentionsRemediationPaths() {
        String msg = AuthErrorMessageMapper.buildMessage("openai", "OPENAI_API_KEY");
        // Names the three ways to fix it: env, credentials API, UI.
        assertThat(msg)
                .containsIgnoringCase("environment")
                .contains("/api/credentials/")
                .containsIgnoringCase("UI");
    }
}
