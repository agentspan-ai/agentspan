/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.List;
import java.util.function.Function;

import javax.crypto.AEADBadTagException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import dev.agentspan.runtime.spi.CredentialStoreProvider;

/**
 * On startup, seeds the credential store from well-known LLM provider environment variables.
 *
 * <p>For each variable in {@link #KNOWN_ENV_VARS} that is set (non-empty), this runner
 * creates a credential under the anonymous OSS user. If a credential with that name already
 * exists the import is silently skipped with a WARN log — the stored value is never
 * overwritten automatically.</p>
 *
 * <p>This removes the need for developers to re-enter API keys they already have in their
 * environment. Set the env var, start the server, and the credential is ready to use.</p>
 *
 * <p>Only runs when {@code agentspan.credentials.store=built-in}. External stores
 * (Vault, AWS SM, etc.) manage their own secrets.</p>
 */
@Component
public class CredentialEnvSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(CredentialEnvSeeder.class);

    /**
     * User ID for the anonymous/OSS user — matches {@code AuthFilter.ANONYMOUS}.
     * In no-auth mode all credentials are stored under this ID.
     */
    static final String ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000";

    /**
     * Well-known provider environment variables to scan on startup.
     *
     * <p>Now sourced from the shared {@link KnownProviderEnvVars#NAMES} in the library so the
     * standalone server and embedding hosts (e.g. orkes-conductor) seed an identical set.</p>
     */
    static final List<String> KNOWN_ENV_VARS = KnownProviderEnvVars.NAMES;

    private final CredentialStoreProvider storeProvider;
    private final Function<String, String> envLookup;

    @Value("${agentspan.credentials.store:built-in}")
    private String credentialsStore;

    /** Production constructor — reads from the real process environment. */
    @Autowired
    public CredentialEnvSeeder(CredentialStoreProvider storeProvider) {
        this(storeProvider, System::getenv);
    }

    /** Package-private constructor for testing — accepts a custom env lookup. */
    CredentialEnvSeeder(CredentialStoreProvider storeProvider, Function<String, String> envLookup) {
        this.storeProvider = storeProvider;
        this.envLookup = envLookup;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!"built-in".equals(credentialsStore)) {
            log.debug("Credential env seeding skipped — store={} is not built-in", credentialsStore);
            return;
        }

        int created = 0;
        int skipped = 0;

        for (String name : KNOWN_ENV_VARS) {
            String value = envLookup.apply(name);
            if (value == null || value.isBlank()) {
                continue;
            }

            String existing;
            try {
                existing = storeProvider.get(ANONYMOUS_USER_ID, name);
            } catch (Exception e) {
                if (!(e.getCause() instanceof AEADBadTagException)) {
                    throw e; // not a key mismatch — propagate (e.g. DB connection failure)
                }
                log.warn(
                        "Credential '{}' could not be decrypted (master key mismatch?) — "
                                + "re-seeding from environment variable",
                        name,
                        e);
                try {
                    storeProvider.delete(ANONYMOUS_USER_ID, name);
                    storeProvider.set(ANONYMOUS_USER_ID, name, value);
                    created++;
                } catch (Exception re) {
                    log.warn("Credential '{}' could not be re-seeded — skipping", name, re);
                }
                continue;
            }

            if (existing != null) {
                log.warn(
                        "Credential '{}' already exists in store — skipping env import. "
                                + "To update the value, use the Credentials UI.",
                        name);
                skipped++;
                continue;
            }

            try {
                storeProvider.set(ANONYMOUS_USER_ID, name, value);
                log.info("Credential seeded from environment: {}", name);
                created++;
            } catch (Exception e) {
                log.warn("Credential '{}' could not be seeded — skipping: {}", name, e.getMessage());
            }
        }

        if (created > 0 || skipped > 0) {
            log.info("Credential env seeding complete: {} created, {} already existed (skipped)", created, skipped);
        }
    }
}
