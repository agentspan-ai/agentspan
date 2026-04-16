/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import java.util.Optional;

import org.springframework.stereotype.Component;

import dev.agentspan.runtime.ai.AgentspanAIModelProvider;
import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class ProviderValidator {

    private final AgentspanAIModelProvider aiModelProvider;

    private static final String DOCS_URL = "https://github.com/agentspan-ai/agentspan/blob/main/docs/ai-models.md";

    /**
     * Returns Optional.empty() if the provider is configured (either via startup environment
     * variables or via a credential added in the UI), or Optional.of(errorMessage) if not.
     */
    public Optional<String> validateProvider(String provider) {
        if (aiModelProvider.isProviderConfigured(provider)) {
            return Optional.empty();
        }
        return Optional.of(
                "Model provider '" + provider + "' is not configured. "
                        + "Add an API key for '" + provider + "' on the Credentials page. "
                        + "Docs: " + DOCS_URL);
    }
}
