/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import dev.agentspan.runtime.ai.AgentspanAIModelProvider;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class ProviderValidator {

    private final AgentspanAIModelProvider aiModelProvider;

    private static final String DOCS_URL = "https://github.com/agentspan-ai/agentspan/blob/main/docs/ai-models.md";

    /**
     * When embedded in a host (e.g. orkes-conductor), Conductor is the authority for model
     * providers and credentials: conductor-ai <b>integrations</b> resolve providers by name,
     * and the host's <b>credential store</b> (AWS SSM / Vault / etc., reached via the
     * {@code CredentialStoreProvider} SPI) supplies raw keys. This standalone pre-flight check
     * only knows AgentSpan's own provider model, so it would wrongly reject host-configured
     * providers. The execution path already delegates to conductor-ai (which resolves or
     * rejects the provider), so when embedded we defer to Conductor and skip this check.
     */
    @Value("${agentspan.embedded:false}")
    private boolean embedded;

    /**
     * Returns Optional.empty() if the provider is configured (either via startup environment
     * variables or via a credential added in the UI), or Optional.of(errorMessage) if not.
     */
    public Optional<String> validateProvider(String provider) {
        if (embedded || aiModelProvider.isProviderConfigured(provider)) {
            return Optional.empty();
        }
        return Optional.of("Model provider '" + provider + "' is not configured. "
                + "Add an API key for '" + provider + "' on the Credentials page. "
                + "Docs: " + DOCS_URL);
    }
}
