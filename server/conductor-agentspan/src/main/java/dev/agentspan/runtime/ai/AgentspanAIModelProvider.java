/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import java.util.List;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.AIModelProvider;
import org.conductoross.conductor.ai.ModelConfiguration;
import org.conductoross.conductor.ai.model.LLMWorkerInput;
import org.conductoross.conductor.ai.providers.anthropic.AnthropicConfiguration;
import org.conductoross.conductor.ai.providers.azureopenai.AzureOpenAIConfiguration;
import org.conductoross.conductor.ai.providers.cohere.CohereAIConfiguration;
import org.conductoross.conductor.ai.providers.gemini.GeminiVertexConfiguration;
import org.conductoross.conductor.ai.providers.grok.GrokAIConfiguration;
import org.conductoross.conductor.ai.providers.huggingface.HuggingFaceConfiguration;
import org.conductoross.conductor.ai.providers.mistral.MistralAIConfiguration;
import org.conductoross.conductor.ai.providers.openai.OpenAIConfiguration;
import org.conductoross.conductor.ai.providers.perplexity.PerplexityAIConfiguration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import com.netflix.conductor.sdk.workflow.executor.task.TaskContext;

import okhttp3.OkHttpClient;

/**
 * LLM model provider that builds a fresh AIModel per call using credentials supplied via the
 * LLM task input.
 *
 * <p>Overrides {@link AIModelProvider#getModel(LLMWorkerInput)}. In EMBEDDED mode the
 * {@code apiKey} (and optional {@code baseUrl}/{@code geminiProjectId}) arrive in the task input
 * as {@code ${workflow.secrets.NAME}} references that the host (orkes-conductor) resolves
 * just-in-time before this in-process LLM system task runs — agentspan resolves nothing itself.
 * STANDALONE (OSS, deliberately non-secure) injects no key, so this falls back to the
 * server-wide {@code System.getenv} key, then to the model configured at startup.</p>
 *
 * <p>Follows the same pattern as Orkes Conductor's {@code OrkesAIModelProvider}.</p>
 */
@Component
@Primary
public class AgentspanAIModelProvider extends AIModelProvider {

    private static final Logger log = LoggerFactory.getLogger(AgentspanAIModelProvider.class);
    private final OkHttpClient conductorAiHttpClient;

    public AgentspanAIModelProvider(
            List<ModelConfiguration<? extends AIModel>> modelConfigurations,
            Environment env,
            OkHttpClient conductorAiHttpClient) {
        super(modelConfigurations, env);
        this.conductorAiHttpClient = conductorAiHttpClient;
        log.info("AgentspanAIModelProvider initialized (host-resolved credential model)");
    }

    @Override
    public AIModel getModel(LLMWorkerInput input) {
        String provider = input.getLlmProvider();
        if (provider == null) {
            return super.getModel(input);
        }

        // Per-agent base URL (host-resolved secret reference or literal) from the task input.
        String baseUrl = readTaskInput("baseUrl");

        // API key: host-resolved value from the task input (embedded), else server-wide env key.
        String apiKey = readTaskInput("apiKey");
        if (apiKey != null || baseUrl != null) {
            try {
                if (apiKey == null) {
                    String envVar = LlmProviderEnv.apiKeyEnv(provider);
                    apiKey = envVar != null ? System.getenv(envVar) : null;
                }
                if (apiKey != null) {
                    AIModel model = createModelWithKey(provider, apiKey, baseUrl);
                    if (model != null) {
                        log.debug("Per-call AIModel created for provider '{}' baseUrl='{}'", provider, baseUrl);
                        getProviderToLLM().put(provider.toLowerCase(), model);
                        return model;
                    }
                }
            } catch (Exception e) {
                log.warn("Failed to create per-call AIModel for '{}': {}", provider, e.getMessage(), e);
            }
        }

        // Fall back to server-wide model
        return super.getModel(input);
    }

    /**
     * Returns true if the provider is available: configured at startup (via environment
     * variables / application.properties). Per-call (task-input) credentials are not visible here.
     */
    public boolean isProviderConfigured(String provider) {
        return getProviderToLLM().containsKey(provider.toLowerCase());
    }

    /**
     * Read an orkes-resolved string from the current task input. Returns null if absent, blank,
     * or still an unresolved {@code ${...}} reference (defensive — never hand a placeholder to the
     * model client).
     */
    private static String readTaskInput(String key) {
        try {
            TaskContext ctx = TaskContext.get();
            if (ctx != null && ctx.getTask() != null) {
                Object v = ctx.getTask().getInputData().get(key);
                if (v instanceof String s && !s.isBlank() && !s.startsWith("${")) {
                    return s;
                }
            }
        } catch (Exception e) {
            // ignore — no task context (e.g. outside worker execution)
        }
        return null;
    }

    /**
     * Create a fresh AIModel instance with an API key and optional base URL.
     */
    private AIModel createModelWithKey(String provider, String apiKey, String baseUrl) {
        ModelConfiguration<? extends AIModel> config =
                switch (provider.toLowerCase()) {
                    case "openai" -> new OpenAIConfiguration(apiKey, baseUrl, null, conductorAiHttpClient);
                    case "anthropic" -> new AnthropicConfiguration(
                            apiKey, baseUrl, null, null, null, conductorAiHttpClient);
                    case "azureopenai" -> new AzureOpenAIConfiguration(
                            apiKey, baseUrl, null, null, conductorAiHttpClient);
                    case "mistral" -> new MistralAIConfiguration(apiKey, baseUrl, conductorAiHttpClient);
                    case "cohere" -> new CohereAIConfiguration(apiKey, baseUrl, conductorAiHttpClient);
                    case "grok" -> new GrokAIConfiguration(apiKey, baseUrl, conductorAiHttpClient);
                    case "huggingface" -> {
                        var c = new HuggingFaceConfiguration();
                        c.setApiKey(apiKey);
                        yield c;
                    }
                    case "perplexity" -> new PerplexityAIConfiguration(apiKey, baseUrl, conductorAiHttpClient);
                    case "gemini", "google_gemini" -> null; // Handled below
                    default -> null;
                };

        if (config != null) {
            return config.get();
        }

        // Gemini uses the upstream configuration object so Conductor owns the concrete model path.
        if (LlmProviderEnv.isGemini(provider)) {
            return createGeminiModel(apiKey);
        }

        return null;
    }

    /**
     * Create a Gemini model using API key auth through the upstream Conductor configuration.
     */
    private AIModel createGeminiModel(String apiKey) {
        String projectId = readTaskInput("geminiProjectId");
        var config = new GeminiVertexConfiguration();
        config.setApiKey(apiKey);
        config.setProjectId(projectId != null ? projectId : "google-ai-studio");
        config.setLocation("us-central1");
        config.setHttpClient(conductorAiHttpClient);
        return config.get();
    }
}
