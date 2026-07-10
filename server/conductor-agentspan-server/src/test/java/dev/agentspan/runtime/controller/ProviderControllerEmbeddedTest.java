/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.Environment;
import org.springframework.test.util.ReflectionTestUtils;

import dev.agentspan.runtime.ai.AgentspanAIModelProvider;

import okhttp3.OkHttpClient;

/**
 * Embedded-mode contract of {@code GET /api/providers/status}.
 *
 * <p>When embedded ({@code agentspan.embedded=true}), the host platform (e.g.
 * orkes-conductor) owns provider integrations and credentials, so the endpoint
 * must defer — {@code managedByHost: true}, no per-provider claims, and no
 * probes — rather than report agentspan's own (wrong there) view. Delegating
 * real status to the host is tracked in
 * <a href="https://github.com/agentspan-ai/agentspan/issues/310">#310</a>;
 * the wire contract here is forward-compatible with it.</p>
 */
class ProviderControllerEmbeddedTest {

    private ProviderController controller(boolean embedded, AgentspanAIModelProvider modelProvider) {
        Environment env = mock(Environment.class);
        when(env.getProperty(anyString(), anyString())).thenAnswer(i -> i.getArgument(1));
        ProviderController controller = new ProviderController(modelProvider, new OkHttpClient(), env);
        ReflectionTestUtils.setField(controller, "embedded", embedded);
        return controller;
    }

    @Test
    void embedded_reportsManagedByHost_withoutQueryingProviderMachinery() {
        AgentspanAIModelProvider modelProvider = mock(AgentspanAIModelProvider.class);

        Map<String, Object> body = controller(true, modelProvider).status();

        assertThat(body.get("managedByHost")).isEqualTo(true);
        assertThat((List<?>) body.get("providers")).isEmpty();
        // The host owns provider config — agentspan's own view must not leak in.
        verifyNoInteractions(modelProvider);
    }

    @Test
    void standalone_reportsProviders_notManagedByHost() {
        AgentspanAIModelProvider modelProvider = mock(AgentspanAIModelProvider.class);
        when(modelProvider.isProviderConfigured(anyString())).thenReturn(false);
        // Loopback discard port — connection refused instantly, probe returns false.
        when(modelProvider.resolveConfiguredBaseUrl("ollama")).thenReturn("http://127.0.0.1:9");

        Map<String, Object> body = controller(false, modelProvider).status();

        assertThat(body.get("managedByHost")).isEqualTo(false);
        assertThat((List<?>) body.get("providers")).isNotEmpty();
        verify(modelProvider, atLeastOnce()).isProviderConfigured(anyString());
    }
}
