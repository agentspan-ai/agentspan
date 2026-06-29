/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.springframework.stereotype.Service;

import dev.agentspan.runtime.spi.SecretOutputMasker;

/**
 * No-op {@link SecretOutputMasker} — the OSS / standalone default.
 *
 * <p>OSS has no per-execution disclosure tracking ({@code credential_disclosures}),
 * so there is nothing to redact against: {@link #mask} returns the payload unchanged.
 *
 * <p>An embedding host (e.g. orkes-conductor) supplies a real implementation that
 * queries the disclosure log, fetches the current plaintext values from the secret
 * store, and redacts them from the response body via a Jackson-tree walk (so values
 * containing newlines, quotes, or other JSON-escaped characters are still caught).
 */
@Service
public class NoOpSecretOutputMasker implements SecretOutputMasker {

    @Override
    public String mask(String executionId, String userId, String payload) {
        return payload;
    }
}
