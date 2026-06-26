/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import java.util.Map;

/**
 * Maps Conductor LLM provider names to their credential / base-URL environment variable
 * (= secret) names. Shared by {@link AgentChatCompleteTaskMapper} (which stamps
 * {@code ${workflow.secrets.NAME}} references into the LLM task input in EMBEDDED mode) and
 * {@link AgentspanAIModelProvider} (which reads the orkes-resolved value, or — STANDALONE —
 * falls back to {@code System.getenv}).
 */
public final class LlmProviderEnv {

    private LlmProviderEnv() {}

    /** Secret/env var name holding the project id for Gemini API-key auth. */
    public static final String GEMINI_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT";

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

    /** Maps Conductor provider names to base URL env var names. */
    public static final Map<String, String> PROVIDER_TO_BASE_URL_ENV = Map.ofEntries(
            Map.entry("openai", "OPENAI_BASE_URL"),
            Map.entry("anthropic", "ANTHROPIC_BASE_URL"),
            Map.entry("mistral", "MISTRAL_BASE_URL"),
            Map.entry("cohere", "COHERE_BASE_URL"),
            Map.entry("grok", "GROK_BASE_URL"),
            Map.entry("perplexity", "PERPLEXITY_BASE_URL"),
            Map.entry("azureopenai", "AZURE_OPENAI_BASE_URL"));

    /** Credential env var name for a provider's API key, or null if unknown. */
    public static String apiKeyEnv(String provider) {
        return provider == null ? null : PROVIDER_TO_ENV_VAR.get(provider.toLowerCase());
    }

    /** Env var name for a provider's base URL, or null if unknown. */
    public static String baseUrlEnv(String provider) {
        return provider == null ? null : PROVIDER_TO_BASE_URL_ENV.get(provider.toLowerCase());
    }

    /** True for Gemini providers, which need an extra project-id secret. */
    public static boolean isGemini(String provider) {
        if (provider == null) return false;
        String p = provider.toLowerCase();
        return p.equals("gemini") || p.equals("google_gemini");
    }
}
