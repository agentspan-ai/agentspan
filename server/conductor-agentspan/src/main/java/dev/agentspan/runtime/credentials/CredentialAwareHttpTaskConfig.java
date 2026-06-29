/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.tasks.http.providers.RestTemplateProvider;

/**
 * Registers {@link CredentialAwareHttpTask} as the primary HTTP system task,
 * overriding Conductor's default HttpTask.
 *
 * <p>This follows the same pattern as {@code AgentHumanTaskConfig} which
 * overrides the default HUMAN task.</p>
 *
 * <p><b>Embedded mode:</b> disabled when {@code agentspan.embedded=true} (e.g. when the
 * library is imported into a host such as orkes-conductor). The host already provides its
 * own {@code HTTP} system task — overriding it here would collide on the {@code "HTTP"} bean
 * name and downgrade the host's task. The host is expected to port {@code #{NAME}} secret
 * resolution into its own HTTP task, guarded by the {@code __agentspan_ctx__} input. The
 * standalone OSS server leaves this property unset, so the override stays active as before.</p>
 */
@Configuration
@ConditionalOnProperty(name = "agentspan.embedded", havingValue = "false", matchIfMissing = true)
public class CredentialAwareHttpTaskConfig {

    @Bean("HTTP")
    @Primary
    public CredentialAwareHttpTask credentialAwareHttpTask(
            RestTemplateProvider restTemplateProvider,
            ObjectMapper objectMapper,
            ExecutionTokenService tokenService,
            CredentialResolutionService resolutionService) {
        return new CredentialAwareHttpTask(restTemplateProvider, objectMapper, tokenService, resolutionService);
    }
}
