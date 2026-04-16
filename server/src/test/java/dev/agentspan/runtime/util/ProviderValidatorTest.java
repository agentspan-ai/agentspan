/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Map;
import java.util.Optional;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.AIModelProvider;
import org.junit.jupiter.api.Test;

class ProviderValidatorTest {

    private ProviderValidator validatorWith(String... configuredProviders) {
        AIModelProvider aiModelProvider = mock(AIModelProvider.class);
        Map<String, AIModel> map = new java.util.HashMap<>();
        for (String p : configuredProviders) {
            map.put(p, mock(AIModel.class));
        }
        when(aiModelProvider.getProviderToLLM()).thenReturn(map);
        return new ProviderValidator(aiModelProvider);
    }

    @Test
    void configuredProviderPasses() {
        ProviderValidator validator = validatorWith("openai");
        assertThat(validator.validateProvider("openai")).isEmpty();
    }

    @Test
    void unconfiguredProviderReturnsError() {
        ProviderValidator validator = validatorWith("anthropic");
        Optional<String> result = validator.validateProvider("openai");
        assertThat(result).isPresent();
        assertThat(result.get()).contains("openai");
    }

    @Test
    void caseInsensitiveLookup() {
        ProviderValidator validator = validatorWith("openai");
        assertThat(validator.validateProvider("OpenAI")).isEmpty();
    }

    @Test
    void errorMessageIncludesDocsUrl() {
        ProviderValidator validator = validatorWith();
        Optional<String> result = validator.validateProvider("mistral");
        assertThat(result).isPresent();
        assertThat(result.get()).contains("mistral").contains("Docs:");
    }

    @Test
    void multipleProvidersConfigured() {
        ProviderValidator validator = validatorWith("openai", "anthropic", "gemini");
        assertThat(validator.validateProvider("openai")).isEmpty();
        assertThat(validator.validateProvider("anthropic")).isEmpty();
        assertThat(validator.validateProvider("gemini")).isEmpty();
        assertThat(validator.validateProvider("mistral")).isPresent();
    }
}
