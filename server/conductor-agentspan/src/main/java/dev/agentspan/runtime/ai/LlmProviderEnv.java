/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import java.util.Map;

/**
 * Maps Conductor LLM provider names to their credential environment-variable (= secret) names.
 * Shared by {@link AgentChatCompleteTaskMapper} (which, in EMBEDDED mode, stamps
 * {@code ${workflow.secrets.NAME}} references into the LLM task input for the host to resolve)
 * and {@link AgentspanAIModelProvider} (which reads the host-resolved value in embedded mode, or
 * resolves natively / falls back to {@code System.getenv} when standalone).
 */
public final class LlmProviderEnv {

    private LlmProviderEnv() {}

    /** Maps Conductor provider names to credential env var names. */
    public static final Map<String, String> PROVIDER_TO_ENV_VAR = Map.ofEntries(
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

    /** Credential env var name for a provider's API key, or {@code null} if unknown. */
    public static String apiKeyEnv(String provider) {
        return provider == null ? null : PROVIDER_TO_ENV_VAR.get(provider.toLowerCase());
    }
}
