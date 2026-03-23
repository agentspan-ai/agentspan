/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.credentials.CredentialResolutionService;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.AIModelProvider;
import org.conductoross.conductor.ai.ModelConfiguration;
import org.conductoross.conductor.ai.models.LLMWorkerInput;
import org.conductoross.conductor.ai.providers.anthropic.AnthropicConfiguration;
import org.conductoross.conductor.ai.providers.azureopenai.AzureOpenAIConfiguration;
import org.conductoross.conductor.ai.providers.cohere.CohereAIConfiguration;
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

import java.util.List;
import java.util.Map;

/**
 * Per-user LLM model provider that creates fresh AIModel instances with
 * API keys from the credential store.
 *
 * <p>Overrides {@link AIModelProvider#getModel(LLMWorkerInput)} to resolve
 * per-user credentials via {@link CredentialResolutionService}. If the user
 * has a credential stored (e.g., {@code OPENAI_API_KEY}), a fresh AIModel
 * is created with that key. Otherwise falls back to the server-wide model
 * configured in application.properties.</p>
 *
 * <p>Follows the same pattern as Orkes Conductor's {@code OrkesAIModelProvider}.</p>
 */
@Component
@Primary
public class AgentspanAIModelProvider extends AIModelProvider {

    private static final Logger log = LoggerFactory.getLogger(AgentspanAIModelProvider.class);

    /** Maps Conductor provider names to credential env var names. */
    private static final Map<String, String> PROVIDER_TO_ENV_VAR = Map.ofEntries(
        Map.entry("openai",      "OPENAI_API_KEY"),
        Map.entry("anthropic",   "ANTHROPIC_API_KEY"),
        Map.entry("mistral",     "MISTRAL_API_KEY"),
        Map.entry("cohere",      "COHERE_API_KEY"),
        Map.entry("grok",        "XAI_API_KEY"),
        Map.entry("perplexity",  "PERPLEXITY_API_KEY"),
        Map.entry("huggingface", "HUGGINGFACE_API_KEY"),
        Map.entry("azureopenai", "AZURE_OPENAI_API_KEY"),
        Map.entry("gemini",      "GEMINI_API_KEY")
    );

    private final CredentialResolutionService resolutionService;
    private final ExecutionTokenService tokenService;

    public AgentspanAIModelProvider(
            List<ModelConfiguration<? extends AIModel>> modelConfigurations,
            Environment env,
            CredentialResolutionService resolutionService,
            ExecutionTokenService tokenService) {
        super(modelConfigurations, env);
        this.resolutionService = resolutionService;
        this.tokenService = tokenService;
        log.info("AgentspanAIModelProvider initialized (per-user credential resolution enabled)");
    }

    @Override
    public AIModel getModel(LLMWorkerInput input) {
        String provider = input.getLlmProvider();
        if (provider == null) {
            return super.getModel(input);
        }

        // Try per-user credential resolution
        String userApiKey = resolveUserApiKey(provider);
        if (userApiKey != null) {
            try {
                AIModel model = createModelWithKey(provider, userApiKey);
                if (model != null) {
                    log.debug("Per-user AIModel created for provider '{}'", provider);
                    return model;
                }
            } catch (Exception e) {
                log.warn("Failed to create per-user AIModel for '{}': {}", provider, e.getMessage());
            }
        }

        // Fall back to server-wide model
        return super.getModel(input);
    }

    /**
     * Resolve a per-user API key for the given LLM provider.
     *
     * <p>Uses the execution token from {@code __agentspan_ctx__} in the current
     * task's input data (via {@code TaskContext}) to identify the user. This works
     * across thread boundaries — unlike RequestContextHolder which is bound to
     * the HTTP request thread.</p>
     *
     * @return per-user API key, or null if not found
     */
    private String resolveUserApiKey(String provider) {
        String envVarName = PROVIDER_TO_ENV_VAR.get(provider.toLowerCase());
        if (envVarName == null) return null;

        // Try TaskContext first (works in worker threads)
        String userId = extractUserIdFromTaskContext();

        // Fall back to RequestContextHolder (works during HTTP request, e.g. compile)
        if (userId == null) {
            userId = RequestContextHolder.get()
                .map(ctx -> ctx.getUser().getId())
                .orElse(null);
        }

        if (userId == null) return null;

        try {
            return resolutionService.resolve(userId, envVarName);
        } catch (Exception e) {
            log.debug("Per-user key not found for provider '{}': {}", provider, e.getMessage());
            return null;
        }
    }

    /**
     * Extract user ID from the execution token in the current task's input data.
     */
    @SuppressWarnings("unchecked")
    private String extractUserIdFromTaskContext() {
        try {
            com.netflix.conductor.sdk.workflow.executor.task.TaskContext ctx =
                com.netflix.conductor.sdk.workflow.executor.task.TaskContext.get();
            if (ctx == null || ctx.getTask() == null) return null;

            Object agentspanCtx = ctx.getTask().getInputData().get("__agentspan_ctx__");
            String token = null;
            if (agentspanCtx instanceof Map<?,?> ctxMap) {
                token = (String) ctxMap.get("execution_token");
            } else if (agentspanCtx instanceof String s) {
                token = s;
            }
            if (token == null) return null;

            return tokenService.validate(token).userId();
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * Create a fresh AIModel instance with a per-user API key.
     * Follows the Orkes ModelConfigurationProvider pattern.
     */
    /**
     * Create a fresh AIModel instance with a per-user API key.
     * Uses the server-wide model's base URL/endpoint config as defaults,
     * only overriding the API key.
     */
    private AIModel createModelWithKey(String provider, String apiKey) {
        // Get the server-wide model to inherit base URL and other config
        AIModel serverModel = getProviderToLLM().get(provider.toLowerCase());
        String baseUrl = null;

        ModelConfiguration<? extends AIModel> config = switch (provider.toLowerCase()) {
            case "openai" -> {
                var c = new OpenAIConfiguration(apiKey, null, null);
                yield c;
            }
            case "anthropic" -> {
                var c = new AnthropicConfiguration(apiKey, null, null, null, null);
                yield c;
            }
            case "azureopenai" -> {
                var c = new AzureOpenAIConfiguration(apiKey, null, null, null);
                yield c;
            }
            case "mistral" -> new MistralAIConfiguration(apiKey, null);
            case "cohere" -> new CohereAIConfiguration(apiKey, null);
            case "grok" -> new GrokAIConfiguration(apiKey, null);
            case "huggingface" -> {
                var c = new HuggingFaceConfiguration();
                c.setApiKey(apiKey);
                yield c;
            }
            case "perplexity" -> new PerplexityAIConfiguration(apiKey, null);
            default -> null;
        };
        return config != null ? config.get() : null;
    }
}
