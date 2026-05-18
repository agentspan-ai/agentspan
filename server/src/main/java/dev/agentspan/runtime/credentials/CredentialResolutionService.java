/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Single authority for credential resolution across all call paths.
 *
 * <p>Two-step pipeline:</p>
 * <ol>
 *   <li>Look up binding: userId + logicalKey → storeName
 *       (if no binding, use logicalKey as storeName directly — convenience shortcut)</li>
 *   <li>Fetch from CredentialStoreProvider using storeName</li>
 * </ol>
 *
 * <p>No env var fallback — the credential store is the source of truth.
 * If a credential is declared on a tool/agent but not in the store, the resolve
 * endpoint returns it as missing so the SDK can report a clear error.</p>
 */
@Service
public class CredentialResolutionService {

    private static final Logger log = LoggerFactory.getLogger(CredentialResolutionService.class);

    private final CredentialStoreProvider storeProvider;
    private final CredentialBindingService bindingService;

    public CredentialResolutionService(CredentialStoreProvider storeProvider, CredentialBindingService bindingService) {
        this.storeProvider = storeProvider;
        this.bindingService = bindingService;
    }

    /**
     * Resolve a logical credential key for a user.
     *
     * @return the plaintext credential value, or null if not found in the store
     */
    public String resolve(String userId, String logicalKey) {
        // Step 1: Look up binding → store name (or use logicalKey directly)
        Optional<String> binding = bindingService.resolve(userId, logicalKey);
        String storeName = binding.orElse(logicalKey);

        // Step 2: Fetch from store
        String value = storeProvider.get(userId, storeName);
        if (value != null) {
            return value;
        }

        log.debug("Credential '{}' not found in store for user '{}'", logicalKey, userId);
        return null;
    }

    public static class CredentialNotFoundException extends RuntimeException {
        public CredentialNotFoundException(String name) {
            super("Credential not found: " + name);
        }
    }
}
