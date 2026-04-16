/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import java.util.Optional;

import org.conductoross.conductor.ai.AIModelProvider;
import org.springframework.stereotype.Component;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class ProviderValidator {

    private final AIModelProvider aiModelProvider;

    private static final String DOCS_URL = "https://github.com/agentspan-ai/agentspan/blob/main/docs/ai-models.md";

    /**
     * Returns Optional.empty() if the provider is configured,
     * or Optional.of(errorMessage) if not.
     */
    public Optional<String> validateProvider(String provider) {
        String key = provider.toLowerCase();
        if (aiModelProvider.getProviderToLLM().containsKey(key)) {
            return Optional.empty();
        }
        return Optional.of(
                "Model provider '" + provider + "' is not configured on the server. " + "Please configure the '"
                        + provider + "' provider and restart the server. " + "Docs: "
                        + DOCS_URL);
    }
}
