/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.List;

import dev.agentspan.runtime.model.credentials.SecretMeta;

/**
 * Strategy interface for credential storage backends.
 *
 * <p>OSS ships {@link EncryptedDbSecretStoreProvider}.
 * Enterprise module implements AWS SM, HashiCorp Vault, Azure KV, GCP SM, etc.
 * All implementations plug into the same {@link SecretResolutionService} pipeline.</p>
 */
public interface SecretStoreProvider {

    /**
     * Retrieve the plaintext value for a credential.
     * Returns null if not found.
     */
    String get(String userId, String name);

    /**
     * Store or update a credential value (encrypted at rest by the implementation).
     */
    void set(String userId, String name, String value);

    /**
     * Delete a credential. No-op if not found.
     */
    void delete(String userId, String name);

    /**
     * List credential metadata for a user.
     * Returns name + partial value + timestamps. Never returns plaintext values.
     */
    List<SecretMeta> list(String userId);
}
