/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.secrets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.tasks.http.providers.RestTemplateProvider;

/**
 * Registers {@link SecretAwareHttpTask} as the primary HTTP system task,
 * overriding Conductor's default HttpTask.
 *
 * <p>This follows the same pattern as {@code AgentHumanTaskConfig} which
 * overrides the default HUMAN task.</p>
 */
@Configuration
public class SecretAwareHttpTaskConfig {

    @Bean("HTTP")
    @Primary
    public SecretAwareHttpTask credentialAwareHttpTask(
            RestTemplateProvider restTemplateProvider,
            ObjectMapper objectMapper,
            ExecutionTokenService tokenService,
            SecretResolutionService resolutionService) {
        return new SecretAwareHttpTask(restTemplateProvider, objectMapper, tokenService, resolutionService);
    }
}
