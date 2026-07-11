/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.model.LLMWorkerInput;
import org.conductoross.conductor.ai.providers.ollama.Ollama;
import org.conductoross.conductor.ai.providers.ollama.OllamaConfiguration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Environment;
import org.springframework.test.util.ReflectionTestUtils;

import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.sdk.workflow.executor.task.TaskContext;

import dev.agentspan.runtime.credentials.CredentialResolutionService;

import okhttp3.OkHttpClient;

/**
 * Ollama base-URL resolution through the per-user provider path.
 *
 * <p>The server is the source of truth for provider configuration. An
 * {@code OLLAMA_BASE_URL} credential in the store (set via UI or
 * {@code agentspan credentials set} — the no-restart prod path) and a
 * per-agent {@code base_url} must reach the model the agent calls, not
 * silently fall back to the startup default of {@code localhost:11434}.</p>
 */
class AgentspanAIModelProviderOllamaTest {

    private static final String REMOTE_URL = "http://gpu-box:11434";

    private CredentialResolutionService credentialService;
    private AgentspanAIModelProvider provider;

    @BeforeEach
    void setUp() {
        credentialService = mock(CredentialResolutionService.class);
        Environment env = mock(Environment.class);
        when(env.getProperty(anyString(), anyString())).thenAnswer(i -> i.getArgument(1));

        provider = new AgentspanAIModelProvider(List.of(), env, new OkHttpClient(), credentialService);
    }

    @AfterEach
    void cleanUp() {
        TaskContext.clear();
    }

    private static LLMWorkerInput ollamaInput() {
        LLMWorkerInput input = new LLMWorkerInput();
        input.setLlmProvider("ollama");
        input.setModel("llama3");
        return input;
    }

    private static String baseUrlOf(AIModel model) {
        assertThat(model).isInstanceOf(Ollama.class);
        OllamaConfiguration config = (OllamaConfiguration) ReflectionTestUtils.getField(model, "config");
        return config.getBaseURL();
    }

    @Test
    void getModel_ollama_usesCredentialStoreBaseUrl() {
        when(credentialService.resolve("OLLAMA_BASE_URL")).thenReturn(REMOTE_URL);

        AIModel model = provider.getModel(ollamaInput());

        assertThat(baseUrlOf(model)).isEqualTo(REMOTE_URL);
    }

    @Test
    void getModel_ollama_usesPerAgentBaseUrlFromTaskInput() {
        when(credentialService.resolve(anyString())).thenReturn(null);
        Task task = new Task();
        task.setStatus(Task.Status.IN_PROGRESS);
        task.setInputData(Map.of("baseUrl", "http://per-agent-host:11434"));
        TaskContext.set(task);

        AIModel model = provider.getModel(ollamaInput());

        assertThat(baseUrlOf(model)).isEqualTo("http://per-agent-host:11434");
    }
}
