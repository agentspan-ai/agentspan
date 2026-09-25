/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.spi;

import java.util.List;

import com.netflix.conductor.dao.SecretsDAO;

import dev.agentspan.runtime.model.credentials.CredentialMeta;

/**
 * AgentSpan's secret storage contract. Extends Conductor's {@link SecretsDAO} so every secret
 * read/write — from the Credentials UI, credential resolution, and env seeding, as well as
 * Conductor's own workflow-secret substitution — goes through one interface.
 *
 * <p>Adds {@link #listWithMeta()}, the one capability {@code SecretsDAO} doesn't carry: metadata
 * (partial display value + timestamps) for the Credentials UI. {@code SecretsDAO#listSecretNames}
 * only returns names.
 *
 * <p>The standalone server ships an encrypted-DB implementation ({@code AgentspanSecretsDAO}); an
 * embedding host (e.g. orkes-conductor) can supply AWS Secrets Manager, HashiCorp Vault, Azure KV,
 * GCP SM, etc.
 */
public interface CredentialsDAO extends SecretsDAO {

    /**
     * List credential metadata for the store — name + partial display value + timestamps.
     * Never returns plaintext values.
     */
    List<CredentialMeta> listWithMeta();
}
