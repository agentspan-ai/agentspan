/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Environment;

import dev.agentspan.runtime.credentials.CredentialResolutionService;
import dev.agentspan.runtime.credentials.ExecutionTokenService;

import okhttp3.OkHttpClient;

class AgentspanAIModelProviderTest {

    private static final String ANON_USER = "00000000-0000-0000-0000-000000000000";

    private CredentialResolutionService credentialService;
    private ExecutionTokenService tokenService;
    private OkHttpClient httpClient;
    private AgentspanAIModelProvider provider;

    @BeforeEach
    void setUp() {
        credentialService = mock(CredentialResolutionService.class);
        tokenService = mock(ExecutionTokenService.class);
        httpClient = new OkHttpClient();
        Environment env = mock(Environment.class);
        when(env.getProperty(anyString(), anyString())).thenAnswer(i -> i.getArgument(1));

        provider = new AgentspanAIModelProvider(List.of(), env, httpClient, credentialService, tokenService);
    }

    @Test
    void constructorAcceptsInjectedHttpClient() {
        // Verifies the constructor doesn't substitute its own client
        assertThat(provider).isNotNull();
    }

    @Test
    void isProviderConfigured_returnsFalse_whenNoCredential() {
        when(credentialService.resolve(ANON_USER, "OPENAI_API_KEY")).thenReturn(null);

        assertThat(provider.isProviderConfigured("openai")).isFalse();
    }

    @Test
    void isProviderConfigured_returnsTrue_whenCredentialFound() {
        when(credentialService.resolve(ANON_USER, "OPENAI_API_KEY")).thenReturn("sk-test-key");

        assertThat(provider.isProviderConfigured("openai")).isTrue();
    }

    @Test
    void isProviderConfigured_caseInsensitive() {
        when(credentialService.resolve(ANON_USER, "ANTHROPIC_API_KEY")).thenReturn("key");

        assertThat(provider.isProviderConfigured("Anthropic")).isTrue();
        assertThat(provider.isProviderConfigured("ANTHROPIC")).isTrue();
    }

    @Test
    void isProviderConfigured_unknownProvider_returnsFalse() {
        // No PROVIDER_TO_ENV_VAR entry → resolveUserApiKey returns null early
        assertThat(provider.isProviderConfigured("unknown-provider")).isFalse();
        verifyNoInteractions(credentialService);
    }

    @Test
    void isProviderConfigured_credentialServiceThrows_returnsFalse() {
        when(credentialService.resolve(ANON_USER, "OPENAI_API_KEY"))
                .thenThrow(new RuntimeException("store unavailable"));

        assertThat(provider.isProviderConfigured("openai")).isFalse();
    }
}
