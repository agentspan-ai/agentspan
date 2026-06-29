/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.List;

/**
 * Single source of truth for the well-known LLM/tool provider environment variables that AgentSpan
 * auto-seeds into the credential store on startup.
 *
 * <p>Shared so every deployment seeds the same set: the standalone server's {@code CredentialEnvSeeder}
 * and any embedding host (e.g. orkes-conductor) reference this list instead of maintaining their own
 * copies. Keeping one list avoids drift between standalone and embedded behavior.</p>
 *
 * <p>{@code AGENTSPAN_MASTER_KEY} is intentionally excluded — it is the encryption master key and must
 * never be stored as a credential.</p>
 */
public final class KnownProviderEnvVars {

    private KnownProviderEnvVars() {}

    /** Well-known provider environment variables to scan on startup. */
    public static final List<String> NAMES = List.of(
            // Anthropic (Claude)
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            // OpenAI (GPT-4, DALL-E, etc.)
            "OPENAI_API_KEY",
            "OPENAI_ORG_ID",
            "OPENAI_BASE_URL",
            // Google Gemini / AI Studio / Vertex AI
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            // Azure OpenAI
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_BASE_URL",
            "AZURE_OPENAI_DEPLOYMENT",
            // Mistral AI
            "MISTRAL_API_KEY",
            "MISTRAL_BASE_URL",
            // Cohere
            "COHERE_API_KEY",
            "COHERE_BASE_URL",
            // xAI / Grok
            "XAI_API_KEY",
            "GROK_BASE_URL",
            // Groq
            "GROQ_API_KEY",
            // Perplexity
            "PERPLEXITY_API_KEY",
            "PERPLEXITY_BASE_URL",
            // HuggingFace
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            // Stability AI
            "STABILITY_API_KEY",
            // DeepSeek
            "DEEPSEEK_API_KEY",
            // Together AI
            "TOGETHER_API_KEY",
            // Replicate
            "REPLICATE_API_TOKEN",
            // GitHub CLI / API
            "GH_TOKEN",
            "GITHUB_TOKEN",
            // AWS Bedrock
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "BEDROCK_API_KEY",
            // Ollama (local inference)
            "OLLAMA_HOST");
}
