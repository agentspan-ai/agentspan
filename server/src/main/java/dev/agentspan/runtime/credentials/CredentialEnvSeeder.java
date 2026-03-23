/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.function.Function;

/**
 * On startup, seeds the credential store from well-known LLM provider environment variables.
 *
 * <p>For each variable in {@link #KNOWN_ENV_VARS} that is set (non-empty), this runner
 * creates a credential under the anonymous OSS user. If a credential with that name already
 * exists the import is silently skipped with a WARN log — the stored value is never
 * overwritten automatically.</p>
 *
 * <p>This removes the need for developers to re-enter API keys they already have in their
 * environment. Set the env var, start the server, and the credential is ready to use.</p>
 *
 * <p>Only runs when {@code agentspan.credentials.store=built-in}. External stores
 * (Vault, AWS SM, etc.) manage their own secrets.</p>
 */
@Component
public class CredentialEnvSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(CredentialEnvSeeder.class);

    /**
     * User ID for the anonymous/OSS user — matches {@code AuthFilter.ANONYMOUS}.
     * In no-auth mode all credentials are stored under this ID.
     */
    static final String ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000";

    /**
     * Well-known provider environment variables to scan on startup.
     * Sourced from the AI provider config in application.properties plus the
     * additional providers listed in the UI quick-select.
     *
     * <p>AGENTSPAN_MASTER_KEY is intentionally excluded — it is the encryption
     * master key and must never be stored as a credential.</p>
     */
    static final List<String> KNOWN_ENV_VARS = List.of(
            // Anthropic (Claude)
            "ANTHROPIC_API_KEY",
            // OpenAI (GPT-4, DALL-E, etc.)
            "OPENAI_API_KEY",
            "OPENAI_ORG_ID",
            // Google Gemini / AI Studio / Vertex AI
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            // Azure OpenAI
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            // Mistral AI
            "MISTRAL_API_KEY",
            // Cohere
            "COHERE_API_KEY",
            // xAI / Grok
            "XAI_API_KEY",
            // Groq
            "GROQ_API_KEY",
            // Perplexity
            "PERPLEXITY_API_KEY",
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
            // AWS Bedrock
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "BEDROCK_API_KEY",
            // Ollama (local inference)
            "OLLAMA_HOST"
    );

    private final CredentialStoreProvider storeProvider;
    private final Function<String, String> envLookup;

    @Value("${agentspan.credentials.store:built-in}")
    private String credentialsStore;

    /** Production constructor — reads from the real process environment. */
    @Autowired
    public CredentialEnvSeeder(CredentialStoreProvider storeProvider) {
        this(storeProvider, System::getenv);
    }

    /** Package-private constructor for testing — accepts a custom env lookup. */
    CredentialEnvSeeder(CredentialStoreProvider storeProvider, Function<String, String> envLookup) {
        this.storeProvider = storeProvider;
        this.envLookup = envLookup;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!"built-in".equals(credentialsStore)) {
            log.debug("Credential env seeding skipped — store={} is not built-in", credentialsStore);
            return;
        }

        int created = 0;
        int skipped = 0;

        for (String name : KNOWN_ENV_VARS) {
            String value = envLookup.apply(name);
            if (value == null || value.isBlank()) {
                continue;
            }

            String existing = storeProvider.get(ANONYMOUS_USER_ID, name);
            if (existing != null) {
                log.warn("Credential '{}' already exists in store — skipping env import. " +
                         "To update the value, use the Credentials UI.", name);
                skipped++;
                continue;
            }

            storeProvider.set(ANONYMOUS_USER_ID, name, value);
            log.info("Credential seeded from environment: {}", name);
            created++;
        }

        if (created > 0 || skipped > 0) {
            log.info("Credential env seeding complete: {} created, {} already existed (skipped)",
                     created, skipped);
        }
    }
}
