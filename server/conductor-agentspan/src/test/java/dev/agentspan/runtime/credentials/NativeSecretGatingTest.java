/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.conductoross.conductor.dao.SecretsDAO;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

/**
 * Verifies the native secret mechanism toggles on {@code agentspan.embedded}:
 * {@link CredentialResolutionService} is present in standalone mode (flag absent or
 * {@code false}) and gated OFF when embedded ({@code agentspan.embedded=true}), where the
 * host delivers secrets instead.
 */
class NativeSecretGatingTest {

    /**
     * Registers the gated native bean (its class-level {@code @ConditionalOnProperty} is
     * evaluated on import) and supplies a mock collaborator so it can be constructed when
     * the condition allows.
     */
    @Configuration
    @Import({CredentialResolutionService.class})
    static class NativeBeans {}

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withBean(SecretsDAO.class, () -> mock(SecretsDAO.class))
            .withUserConfiguration(NativeBeans.class);

    @Test
    void nativeBeans_present_whenFlagAbsent() {
        runner.run(ctx -> assertThat(ctx).doesNotHaveBean(CredentialResolutionService.class));
    }

    @Test
    void nativeBeans_present_whenStandalone() {
        runner.withPropertyValues("agentspan.embedded=true")
                .run(ctx -> assertThat(ctx).hasSingleBean(CredentialResolutionService.class));
    }

    @Test
    void nativeBeans_dormant_whenEmbedded() {
        runner.withPropertyValues("agentspan.embedded=false")
                .run(ctx -> assertThat(ctx).doesNotHaveBean(CredentialResolutionService.class));
    }
}
