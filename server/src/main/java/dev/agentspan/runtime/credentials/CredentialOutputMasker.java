/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.springframework.stereotype.Service;

/**
 * No-op credential masker for the OSS edition.
 *
 * <p>In OSS, disclosure tracking ({@code credential_disclosures}) is not
 * implemented, so there is no per-execution list of resolved credential names
 * to mask against — {@link #mask} returns the payload unchanged.</p>
 *
 * <p>The enterprise module replaces this bean with a real implementation that
 * queries the disclosure log, fetches the current plaintext values from the
 * credential store, and redacts them from the response body using a
 * Jackson-tree walk (so values containing newlines, quotes, or other
 * JSON-escaped characters are still caught).</p>
 */
@Service
public class CredentialOutputMasker {

    /**
     * Returns {@code payload} unchanged.
     * Enterprise override applies redaction based on per-execution disclosures.
     */
    public String mask(String executionId, String userId, String payload) {
        return payload;
    }
}
