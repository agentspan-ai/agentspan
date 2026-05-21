/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.ModelConfiguration;
import org.conductoross.conductor.ai.models.LLMWorkerInput;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Environment;

import dev.agentspan.runtime.credentials.CredentialResolutionService;
import dev.agentspan.runtime.credentials.ExecutionTokenService;

/**
 * Unit tests for the empty-key fail-fast path added to
 * {@link AgentspanAIModelProvider#getModel(LLMWorkerInput)}.
 *
 * <p>Background: when the server was started with an EMPTY env var (e.g. due
 * to a {@code .zshrc} typo), Spring AI silently configured the provider bean
 * with {@code ""} and the provider would later return 401 mid-stream with the
 * misleading "cannot retry due to server authentication" message. The new
 * code throws {@link IllegalStateException} before making the doomed call.</p>
 */
class AgentspanAIModelProviderTest {

    /** Mockable provider that lets the test inject a fake env lookup. */
    static class TestProvider extends AgentspanAIModelProvider {
        private final Map<String, String> env;

        TestProvider(
                CredentialResolutionService resolutionService,
                ExecutionTokenService tokenService,
                Map<String, String> env) {
            super(List.<ModelConfiguration<? extends AIModel>>of(), mock(Environment.class), resolutionService, tokenService);
            this.env = env;
        }

        @Override
        String lookupEnv(String name) {
            return env.get(name);
        }
    }

    private CredentialResolutionService mockResolutionService(String userKey) {
        CredentialResolutionService svc = mock(CredentialResolutionService.class);
        try {
            if (userKey == null) {
                when(svc.resolve(anyString(), anyString())).thenReturn(null);
            } else {
                when(svc.resolve(anyString(), anyString())).thenReturn(userKey);
            }
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        return svc;
    }

    private LLMWorkerInput input(String provider, String model) {
        LLMWorkerInput in = new LLMWorkerInput();
        in.setLlmProvider(provider);
        in.setModel(model);
        return in;
    }

    @Test
    void throwsWhenEnvVarEmptyAndNoCredential() {
        // .zshrc-typo reproducer: env var is set but EMPTY, no per-user credential.
        Map<String, String> env = new HashMap<>();
        env.put("ANTHROPIC_API_KEY", ""); // empty, like Spring's ${ANTHROPIC_API_KEY:} default

        TestProvider provider = new TestProvider(
                mockResolutionService(null), mock(ExecutionTokenService.class), env);

        assertThatThrownBy(() -> provider.getModel(input("anthropic", "claude-3-5-sonnet")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("anthropic")
                .hasMessageContaining("ANTHROPIC_API_KEY")
                .hasMessageContaining("PUT /api/credentials");
    }

    @Test
    void throwsWhenEnvVarMissingAndNoCredential() {
        // Env var completely absent (System.getenv returns null), no per-user credential.
        Map<String, String> env = new HashMap<>(); // ANTHROPIC_API_KEY not present

        TestProvider provider = new TestProvider(
                mockResolutionService(null), mock(ExecutionTokenService.class), env);

        assertThatThrownBy(() -> provider.getModel(input("anthropic", "claude-3-5-sonnet")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("ANTHROPIC_API_KEY");
    }

    @Test
    void doesNotThrowWhenBlankCredentialButValidEnvVar() {
        // Per-user credential is blank (would be ignored), env var has a real key.
        // Spring AI bean is properly configured, fall-through to super is safe.
        // (We don't reach super in this stub — but the absence of IllegalStateException
        // proves the fail-fast did not fire.)
        Map<String, String> env = new HashMap<>();
        env.put("ANTHROPIC_API_KEY", "sk-ant-real-key");

        TestProvider provider = new TestProvider(
                mockResolutionService("   "), mock(ExecutionTokenService.class), env);

        // The provider may return null from super.getModel (since we didn't wire one),
        // but the important behavior is that no IllegalStateException is thrown.
        try {
            provider.getModel(input("anthropic", "claude-3-5-sonnet"));
        } catch (IllegalStateException e) {
            throw new AssertionError("Should not have thrown — env var is set", e);
        } catch (Exception ignored) {
            // super.getModel may throw something else (model not registered) — that's fine.
        }
    }

    @Test
    void doesNotThrowForUnknownProvider() {
        // Provider not in PROVIDER_TO_ENV_VAR map (no envVar resolved) — skip the
        // fail-fast so unknown/custom providers fall through to super untouched.
        Map<String, String> env = new HashMap<>();

        TestProvider provider = new TestProvider(
                mockResolutionService(null), mock(ExecutionTokenService.class), env);

        try {
            provider.getModel(input("some-custom-provider", "some-model"));
        } catch (IllegalStateException e) {
            throw new AssertionError("Should not throw for unknown provider", e);
        } catch (Exception ignored) {
            // super may throw — that's not our concern here.
        }
    }

    @Test
    void blankCredentialIsTreatedAsMissing() {
        // Per-user credential exists but is blank ("  "). The provider should NOT
        // try to build a model with it. Combined with a valid env var → no throw.
        // Combined with a missing env var → throws the fail-fast.
        Map<String, String> env = new HashMap<>(); // no env var
        TestProvider provider = new TestProvider(
                mockResolutionService("   "), mock(ExecutionTokenService.class), env);

        assertThatThrownBy(() -> provider.getModel(input("anthropic", "claude-3-5-sonnet")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("ANTHROPIC_API_KEY");
    }

    @Test
    void errorMessageNamesCorrectEnvVarPerProvider() {
        Map<String, String> env = new HashMap<>();
        TestProvider provider = new TestProvider(
                mockResolutionService(null), mock(ExecutionTokenService.class), env);

        // OpenAI → OPENAI_API_KEY
        assertThatThrownBy(() -> provider.getModel(input("openai", "gpt-4o")))
                .hasMessageContaining("OPENAI_API_KEY");
        // Mistral → MISTRAL_API_KEY
        assertThatThrownBy(() -> provider.getModel(input("mistral", "mistral-large")))
                .hasMessageContaining("MISTRAL_API_KEY");
    }
}
