/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.List;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import com.netflix.conductor.dao.SecretsDAO;

import dev.agentspan.runtime.model.credentials.CredentialMeta;
import dev.agentspan.runtime.spi.CredentialStoreProvider;

/**
 * Bridges conductor's global {@link SecretsDAO} to AgentSpan's own {@link CredentialStoreProvider}
 * (the encrypted credential store), scoped to the anonymous/system user.
 *
 * <p>Active only when {@code conductor.secrets.type=agentspan} — the "agentspan-as-host" mode where
 * the AgentSpan server embeds conductor ({@code agentspan.embedded=true}) <em>and</em> also serves as
 * the secret-resolving host. In that mode the embedded conductor's {@code RuntimeMetadataResolver}
 * calls {@link #getSecret(String)} at each SIMPLE task's poll to resolve the secret names a worker
 * declared on {@code TaskDef.runtimeMetadata}, injecting the resolved values onto the wire-only
 * {@code Task.runtimeMetadata}. Selecting this DAO ({@code havingValue="agentspan"}) gates conductor's
 * own env-variable / noop {@code SecretsDAO} implementations off (they require
 * {@code conductor.secrets.type} to be {@code env}/absent or {@code noop}).</p>
 *
 * <p>Conductor secrets are global (name only); AgentSpan's store is per-user, so every lookup is
 * scoped to {@link #ANONYMOUS_USER_ID} — the no-auth/system user, matching {@code CredentialEnvSeeder}
 * and {@code AuthFilter.ANONYMOUS}. Names are treated as flat keys (no dotted JSONPath): worker
 * credential names are simple identifiers, and {@link CredentialStoreProvider#get} resolves them
 * directly.</p>
 *
 * <p>The backing store beans ({@code EncryptedDbCredentialStoreProvider}, {@code MasterKeyConfig},
 * {@code CredentialDataSourceConfig}, {@code CredentialSchemaMigrator}) are normally dormant when
 * embedded; they are re-enabled under this same {@code conductor.secrets.type=agentspan} flag so this
 * bridge has a store to read from.</p>
 */
@Component
@ConditionalOnProperty(name = "conductor.secrets.type", havingValue = "agentspan")
public class AgentspanSecretsDAO implements SecretsDAO {

    private static final Logger log = LoggerFactory.getLogger(AgentspanSecretsDAO.class);

    /**
     * User ID for the anonymous/OSS user — matches {@code CredentialEnvSeeder.ANONYMOUS_USER_ID} and
     * {@code AuthFilter.ANONYMOUS}. Conductor's global secret lookups resolve against this user.
     */
    static final String ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000";

    private final CredentialStoreProvider store;

    public AgentspanSecretsDAO(CredentialStoreProvider store) {
        this.store = store;
        log.info(
                "AgentspanSecretsDAO active — embedded conductor secrets resolve from the AgentSpan "
                        + "credential store (scoped to system user {})",
                ANONYMOUS_USER_ID);
    }

    @Override
    public String getSecret(String key) {
        return store.get(ANONYMOUS_USER_ID, key);
    }

    @Override
    public boolean secretExists(String key) {
        return store.get(ANONYMOUS_USER_ID, key) != null;
    }

    @Override
    public List<String> listSecretNames() {
        return store.list(ANONYMOUS_USER_ID).stream()
                .map(CredentialMeta::getName)
                .collect(Collectors.toList());
    }

    @Override
    public void putSecret(String key, String value) {
        store.set(ANONYMOUS_USER_ID, key, value);
    }

    @Override
    public void deleteSecret(String key) {
        store.delete(ANONYMOUS_USER_ID, key);
    }
}
