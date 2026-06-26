/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Environment;

import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.sdk.workflow.executor.task.TaskContext;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.models.LLMWorkerInput;

import okhttp3.OkHttpClient;

class AgentspanAIModelProviderTest {

    private OkHttpClient httpClient;
    private AgentspanAIModelProvider provider;

    @BeforeEach
    void setUp() {
        httpClient = new OkHttpClient();
        Environment env = mock(Environment.class);
        when(env.getProperty(anyString(), anyString())).thenAnswer(i -> i.getArgument(1));

        // No startup model configurations — provider map is empty, so the only way getModel()
        // builds a model is from the task-input credential (host-resolved, as in embedded mode).
        provider = new AgentspanAIModelProvider(List.of(), env, httpClient);
    }

    @AfterEach
    void tearDown() {
        TaskContext.TASK_CONTEXT_INHERITABLE_THREAD_LOCAL.remove();
    }

    @Test
    void constructorAcceptsInjectedHttpClient() {
        assertThat(provider).isNotNull();
    }

    @Test
    void getModel_buildsModel_fromHostResolvedApiKeyInTaskInput() {
        // Embedded: orkes has resolved ${workflow.secrets.OPENAI_API_KEY} into the task input.
        Task task = new Task();
        task.setStatus(Task.Status.IN_PROGRESS);
        task.setInputData(Map.of("apiKey", "sk-resolved-test-key"));
        TaskContext.set(task);

        LLMWorkerInput input = new LLMWorkerInput();
        input.setLlmProvider("openai");

        AIModel model = provider.getModel(input);

        assertThat(model).isNotNull();
        // The freshly built per-call model is cached under the provider name.
        assertThat(provider.isProviderConfigured("openai")).isTrue();
    }

    @Test
    void getModel_unresolvedReferenceInTaskInput_isIgnored() {
        // Defensive: a literal "${...}" must never be handed to the model client as a key.
        Task task = new Task();
        task.setStatus(Task.Status.IN_PROGRESS);
        task.setInputData(Map.of("apiKey", "${workflow.secrets.OPENAI_API_KEY}"));
        TaskContext.set(task);

        LLMWorkerInput input = new LLMWorkerInput();
        input.setLlmProvider("openai");

        // No usable key (placeholder ignored, no env key, no startup config) → falls through to
        // super.getModel, which has no registered model and throws. Crucially, no per-call model
        // was built from the placeholder string.
        assertThatThrownBy(() -> provider.getModel(input)).isInstanceOf(RuntimeException.class);
        assertThat(provider.isProviderConfigured("openai")).isFalse();
    }

    @Test
    void isProviderConfigured_falseWhenNotConfiguredAtStartup() {
        // No store, no startup model map → nothing is configured ahead of an actual call.
        assertThat(provider.isProviderConfigured("openai")).isFalse();
        assertThat(provider.isProviderConfigured("anthropic")).isFalse();
        assertThat(provider.isProviderConfigured("unknown-provider")).isFalse();
    }
}
