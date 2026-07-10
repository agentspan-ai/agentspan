/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import dev.agentspan.runtime.controller.WorkerController;
import dev.agentspan.runtime.spi.CredentialStoreProvider;

/**
 * Verifies the native secret mechanism toggles on {@code agentspan.embedded}:
 * its beans are present in standalone mode (flag absent or {@code false}) and
 * gated OFF when embedded ({@code agentspan.embedded=true}), where the host
 * delivers secrets instead.
 */
class NativeSecretGatingTest {

    /**
     * Registers the gated native beans (their class-level {@code @ConditionalOnProperty}
     * is evaluated on import) and supplies mock collaborators so they can be constructed
     * when the condition allows.
     */
    @Configuration
    @Import({WorkerController.class, CredentialResolutionService.class, ExecutionTokenService.class})
    static class NativeBeans {}

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withBean(CredentialStoreProvider.class, () -> mock(CredentialStoreProvider.class))
            .withBean("credentialMasterKey", byte[].class, () -> new byte[32])
            .withUserConfiguration(NativeBeans.class);

    @Test
    void nativeBeans_present_whenFlagAbsent() {
        runner.run(ctx -> assertThat(ctx)
                .hasSingleBean(WorkerController.class)
                .hasSingleBean(CredentialResolutionService.class)
                .hasSingleBean(ExecutionTokenService.class));
    }

    @Test
    void nativeBeans_present_whenStandalone() {
        runner.withPropertyValues("agentspan.embedded=false").run(ctx -> assertThat(ctx)
                .hasSingleBean(WorkerController.class)
                .hasSingleBean(CredentialResolutionService.class)
                .hasSingleBean(ExecutionTokenService.class));
    }

    @Test
    void nativeBeans_dormant_whenEmbedded() {
        runner.withPropertyValues("agentspan.embedded=true").run(ctx -> assertThat(ctx)
                .doesNotHaveBean(WorkerController.class)
                .doesNotHaveBean(CredentialResolutionService.class)
                .doesNotHaveBean(ExecutionTokenService.class));
    }
}
