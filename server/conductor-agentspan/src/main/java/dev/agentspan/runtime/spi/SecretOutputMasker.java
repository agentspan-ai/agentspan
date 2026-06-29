/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.spi;

/**
 * Redacts secret values from execution-read responses before they leave the server.
 *
 * <p>The standalone server ships a no-op implementation (OSS has no per-execution
 * disclosure tracking, so there is nothing to redact against). An embedding host
 * (e.g. orkes-conductor) supplies an implementation that looks up the secrets
 * disclosed during an execution and removes their plaintext from the payload.
 *
 * <p>Wired into responses by {@code CredentialMaskingResponseAdvice}.
 */
public interface SecretOutputMasker {

    /**
     * Return {@code payload} with any secrets disclosed for {@code executionId}
     * (scoped to {@code userId}) redacted. Implementations must be best-effort and
     * must never throw — return the payload unchanged on any failure.
     */
    String mask(String executionId, String userId, String payload);
}
