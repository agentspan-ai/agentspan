/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.AIModelProvider;
import org.conductoross.conductor.ai.ModelConfiguration;
import org.conductoross.conductor.ai.models.LLMWorkerInput;
import org.conductoross.conductor.ai.providers.anthropic.AnthropicConfiguration;
import org.conductoross.conductor.ai.providers.azureopenai.AzureOpenAIConfiguration;
import org.conductoross.conductor.ai.providers.cohere.CohereAIConfiguration;
import org.conductoross.conductor.ai.providers.gemini.GeminiVertex;
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

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.credentials.CredentialResolutionService;
import dev.agentspan.runtime.credentials.ExecutionTokenService;

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
            Map.entry("openai", "OPENAI_API_KEY"),
            Map.entry("anthropic", "ANTHROPIC_API_KEY"),
            Map.entry("mistral", "MISTRAL_API_KEY"),
            Map.entry("cohere", "COHERE_API_KEY"),
            Map.entry("grok", "XAI_API_KEY"),
            Map.entry("perplexity", "PERPLEXITY_API_KEY"),
            Map.entry("huggingface", "HUGGINGFACE_API_KEY"),
            Map.entry("azureopenai", "AZURE_OPENAI_API_KEY"),
            Map.entry("gemini", "GEMINI_API_KEY"),
            Map.entry("google_gemini", "GEMINI_API_KEY"));

    /** Maps Conductor provider names to base URL env var names. */
    private static final Map<String, String> PROVIDER_TO_BASE_URL_ENV = Map.ofEntries(
            Map.entry("openai", "OPENAI_BASE_URL"),
            Map.entry("anthropic", "ANTHROPIC_BASE_URL"),
            Map.entry("mistral", "MISTRAL_BASE_URL"),
            Map.entry("cohere", "COHERE_BASE_URL"),
            Map.entry("grok", "GROK_BASE_URL"),
            Map.entry("perplexity", "PERPLEXITY_BASE_URL"),
            Map.entry("azureopenai", "AZURE_OPENAI_BASE_URL"));

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

        // Resolve per-agent base URL (from task input) or env var fallback
        String baseUrl = resolveBaseUrl(provider);

        // Try per-user credential resolution
        log.debug("getModel called for provider='{}' model='{}'", provider, input.getModel());
        String userApiKey = resolveUserApiKey(provider);
        log.debug("resolveUserApiKey('{}') returned: {}", provider, userApiKey != null ? "key found" : "null");
        if (userApiKey != null || baseUrl != null) {
            try {
                // If we have a base URL but no user key, try the server-wide key
                if (userApiKey == null) {
                    String envVar = PROVIDER_TO_ENV_VAR.get(provider.toLowerCase());
                    userApiKey = envVar != null ? System.getenv(envVar) : null;
                }
                if (userApiKey != null) {
                    AIModel model = createModelWithKey(provider, userApiKey, baseUrl);
                    if (model != null) {
                        log.debug("Per-user AIModel created for provider '{}' baseUrl='{}'", provider, baseUrl);
                        getProviderToLLM().put(provider.toLowerCase(), model);
                        return model;
                    }
                }
            } catch (Exception e) {
                log.warn("Failed to create per-user AIModel for '{}': {}", provider, e.getMessage(), e);
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
            userId =
                    RequestContextHolder.get().map(ctx -> ctx.getUser().getId()).orElse(null);
        }

        // Fall back to anonymous user (OSS / no-auth mode)
        if (userId == null) {
            userId = "00000000-0000-0000-0000-000000000000";
        }

        try {
            return resolutionService.resolve(userId, envVarName);
        } catch (Exception e) {
            log.debug("Credential not found for provider '{}': {}", provider, e.getMessage());
            return null;
        }
    }

    /**
     * Extract user ID from the execution token in the current task's input data.
     */
    @SuppressWarnings("unchecked")
    private String extractUserIdFromTaskContext() {
        try {
            TaskContext ctx = TaskContext.get();
            if (ctx == null || ctx.getTask() == null) return null;

            Object agentspanCtx = ctx.getTask().getInputData().get("__agentspan_ctx__");
            String token = null;
            if (agentspanCtx instanceof Map<?, ?> ctxMap) {
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
     * Resolve any named credential for the current user.
     */
    private String resolveUserCredential(String credentialName) {
        String userId = extractUserIdFromTaskContext();
        if (userId == null) {
            userId =
                    RequestContextHolder.get().map(ctx -> ctx.getUser().getId()).orElse(null);
        }
        if (userId == null) {
            userId = "00000000-0000-0000-0000-000000000000";
        }
        try {
            return resolutionService.resolve(userId, credentialName);
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * Resolve base URL: per-agent (from task input) > env var > null (use provider default).
     */
    @SuppressWarnings("unchecked")
    private String resolveBaseUrl(String provider) {
        // 1. Per-agent base URL from task input
        try {
            TaskContext ctx = TaskContext.get();
            if (ctx != null && ctx.getTask() != null) {
                Object taskBaseUrl = ctx.getTask().getInputData().get("baseUrl");
                if (taskBaseUrl instanceof String s && !s.isBlank()) {
                    log.debug("Using per-agent baseUrl for provider '{}': {}", provider, s);
                    return s;
                }
            }
        } catch (Exception e) {
            // ignore
        }

        // 2. Env var fallback (e.g. OPENAI_BASE_URL)
        String envVarName = PROVIDER_TO_BASE_URL_ENV.get(provider.toLowerCase());
        if (envVarName != null) {
            String envVal = System.getenv(envVarName);
            if (envVal != null && !envVal.isBlank()) {
                log.debug("Using env var {} for provider '{}': {}", envVarName, provider, envVal);
                return envVal;
            }
        }

        return null;
    }

    /**
     * Create a fresh AIModel instance with a per-user API key and optional base URL.
     */
    private AIModel createModelWithKey(String provider, String apiKey, String baseUrl) {
        ModelConfiguration<? extends AIModel> config =
                switch (provider.toLowerCase()) {
                    case "openai" -> new OpenAIConfiguration(apiKey, baseUrl, null);
                    case "anthropic" -> new AnthropicConfiguration(apiKey, baseUrl, null, null, null);
                    case "azureopenai" -> new AzureOpenAIConfiguration(apiKey, baseUrl, null, null);
                    case "mistral" -> new MistralAIConfiguration(apiKey, baseUrl);
                    case "cohere" -> new CohereAIConfiguration(apiKey, baseUrl);
                    case "grok" -> new GrokAIConfiguration(apiKey, baseUrl);
                    case "huggingface" -> {
                        var c = new HuggingFaceConfiguration();
                        c.setApiKey(apiKey);
                        yield c;
                    }
                    case "perplexity" -> new PerplexityAIConfiguration(apiKey, baseUrl);
                    case "gemini", "google_gemini" -> null; // Handled below
                    default -> null;
                };

        if (config != null) {
            return config.get();
        }

        // Gemini with API key: use REST transport (AI Studio), not gRPC (Vertex AI)
        String providerLower = provider.toLowerCase();
        if (providerLower.equals("gemini") || providerLower.equals("google_gemini")) {
            return createGeminiApiKeyModel(apiKey);
        }

        return null;
    }

    /**
     * Create a Gemini model using API key auth via REST transport.
     * Uses the upstream GeminiVertex which handles the API key path properly
     * with GoogleGenAiChatModel (full tool calling support).
     */
    private AIModel createGeminiApiKeyModel(String apiKey) {
        String projectId = resolveUserCredential("GOOGLE_CLOUD_PROJECT");
        var config = new GeminiVertexConfiguration();
        config.setApiKey(apiKey);
        config.setProjectId(projectId != null ? projectId : "google-ai-studio");
        config.setLocation("us-central1");
        return new GeminiVertex(config);
    }
}
