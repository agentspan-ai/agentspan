/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.tasks.http.providers.RestTemplateProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/**
 * Registers {@link CredentialAwareHttpTask} as the primary HTTP system task,
 * overriding Conductor's default HttpTask.
 *
 * <p>This follows the same pattern as {@code AgentHumanTaskConfig} which
 * overrides the default HUMAN task.</p>
 */
@Configuration
public class CredentialAwareHttpTaskConfig {

    @Bean("HTTP")
    @Primary
    public CredentialAwareHttpTask credentialAwareHttpTask(
            RestTemplateProvider restTemplateProvider,
            ObjectMapper objectMapper,
            ExecutionTokenService tokenService,
            CredentialResolutionService resolutionService) {
        return new CredentialAwareHttpTask(
            restTemplateProvider, objectMapper, tokenService, resolutionService);
    }
}
