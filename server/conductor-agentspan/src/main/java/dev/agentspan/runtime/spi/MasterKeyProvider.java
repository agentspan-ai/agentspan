/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.spi;

/**
 * Strategy interface for sourcing the AES-256 master key used to protect credentials at rest
 * (AES-256-GCM in the encrypted store) and to sign execution tokens (HMAC-SHA256).
 *
 * <p>The standalone server ships a file/env implementation (key from {@code AGENTSPAN_MASTER_KEY},
 * else auto-generated and persisted to {@code ~/.agentspan/master.key}); an embedding host
 * (e.g. orkes-conductor) can supply AWS KMS, HashiCorp Vault, Azure Key Vault, GCP KMS, etc.
 * All implementations feed the same key material into the credential-crypto pipeline.</p>
 */
public interface MasterKeyProvider {

    /**
     * Return the 32-byte (256-bit) master key. Implementations must return the same key for the
     * lifetime of the process — losing or rotating it invalidates all stored credentials and any
     * outstanding execution tokens.
     */
    byte[] getMasterKey();
}
