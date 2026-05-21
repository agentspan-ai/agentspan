/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime;

import java.net.InetAddress;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.data.mongo.MongoDataAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.mongo.MongoAutoConfiguration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.annotation.EnableScheduling;

import dev.agentspan.runtime.credentials.CredentialEnvSeeder;

import lombok.RequiredArgsConstructor;

@SpringBootApplication(
        exclude = {DataSourceAutoConfiguration.class, MongoAutoConfiguration.class, MongoDataAutoConfiguration.class})
@EnableScheduling
@ComponentScan(
        basePackages = {
            "com.netflix.conductor",
            "io.orkes.conductor",
            "org.conductoross.conductor",
            "dev.agentspan.runtime"
        })
@RequiredArgsConstructor
@Order(Ordered.HIGHEST_PRECEDENCE + 1000)
public class AgentRuntime implements ApplicationRunner {

    private final Logger log = LoggerFactory.getLogger(AgentRuntime.class);

    private final Environment environment;

    @Autowired(required = false)
    private CredentialEnvSeeder credentialEnvSeeder;

    public static void main(String[] args) {
        SpringApplication.run(AgentRuntime.class, args);
    }

    @Override
    public void run(ApplicationArguments args) {
        String dbType = environment.getProperty("conductor.db.type", "memory");
        String queueType = environment.getProperty("conductor.queue.type", "memory");
        String indexingType = environment.getProperty("conductor.indexing.type", "memory");
        String port = environment.getProperty("server.port", "6767");
        String contextPath = environment.getProperty("server.servlet.context-path", "");

        String hostname;
        try {
            hostname = InetAddress.getLocalHost().getHostName();
        } catch (Exception e) {
            hostname = "localhost";
        }

        String serverUrl = String.format("http://%s:%s%s", hostname, port, contextPath);
        log.info("\n\n\n");
        log.info("┌────────────────────────────────────────────────────────────────────────┐");
        log.info("│                    AGENTSPAN SERVER CONFIGURATION                      │");
        log.info("├────────────────────────────────────────────────────────────────────────┤");
        log.info("│  Database Type    : {}", padRight(dbType, 51) + "│");
        log.info("│  Queue Type       : {}", padRight(queueType, 51) + "│");
        log.info("│  Indexing Type    : {}", padRight(indexingType, 51) + "│");
        log.info("│  Server Port      : {}", padRight(port, 51) + "│");
        log.info("├────────────────────────────────────────────────────────────────────────┤");
        log.info("│  Server URL       : {}", padRight(serverUrl, 51) + "│");
        log.info("│  API Docs         : {}", padRight(serverUrl + "/docs/", 51) + "│");
        log.info("└────────────────────────────────────────────────────────────────────────┘");
        log.info("\n\n\n");

        checkAIProviders(environment);
        warnOnStoredCredentialMismatch();
    }

    /**
     * Surface any env-vs-stored credential mismatch detected by the seeder so
     * a user who's fat-fingered an API key and re-exported it sees on the
     * very next server start that the cached value is still winning.
     */
    private void warnOnStoredCredentialMismatch() {
        if (credentialEnvSeeder == null) return;
        var mismatched = credentialEnvSeeder.getLastMismatchedNames();
        if (mismatched.isEmpty()) return;

        log.warn("┌─────────────────────────────────────────────────────────────────┐");
        log.warn("│  STORED CREDENTIAL DIFFERS FROM ENVIRONMENT                     │");
        log.warn("│                                                                 │");
        log.warn("│  The following env vars are SET but differ from the cached      │");
        log.warn("│  credential the server is using:                                │");
        for (String name : mismatched) {
            log.warn("│    - {}", padRight(name, 58) + "│");
        }
        log.warn("│                                                                 │");
        log.warn("│  The CACHED value is being used. To update the stored value:    │");
        log.warn("│    agentspan credentials set NAME \"$NAME\"                     │");
        log.warn("│  or PUT /api/credentials/NAME or use the Credentials UI.        │");
        log.warn("└─────────────────────────────────────────────────────────────────┘");
    }

    private void checkAIProviders(Environment env) {
        Map<String, String> providers = Map.ofEntries(
                Map.entry("OpenAI", "conductor.ai.openai.api-key"),
                Map.entry("Anthropic", "conductor.ai.anthropic.api-key"),
                Map.entry("Google Gemini", "conductor.ai.gemini.api-key"),
                Map.entry("Mistral", "conductor.ai.mistral.api-key"),
                Map.entry("Cohere", "conductor.ai.cohere.api-key"),
                Map.entry("Grok", "conductor.ai.grok.api-key"),
                Map.entry("Perplexity", "conductor.ai.perplexity.api-key"),
                Map.entry("HuggingFace", "conductor.ai.huggingface.api-key"),
                Map.entry("Azure OpenAI", "conductor.ai.azureopenai.api-key"),
                Map.entry("AWS Bedrock", "conductor.ai.bedrock.access-key"));

        boolean hasAny = providers.values().stream().anyMatch(prop -> {
            String val = env.getProperty(prop);
            return val != null && !val.isBlank();
        });

        if (!hasAny) {
            log.warn("┌─────────────────────────────────────────────────────────────────┐");
            log.warn("│  WARNING: No AI provider API keys configured!                   │");
            log.warn("│                                                                 │");
            log.warn("│  Agents will fail until at least one provider is configured.    │");
            log.warn("│  Set environment variables before starting the server:          │");
            log.warn("│                                                                 │");
            log.warn("│    export OPENAI_API_KEY=sk-...                                 │");
            log.warn("│    export ANTHROPIC_API_KEY=sk-ant-...                          │");
            log.warn("│                                                                 │");
            log.warn("│  Docs: https://github.com/agentspan-ai/agentspan/blob/main/docs/ai-models.md");
            log.warn("└─────────────────────────────────────────────────────────────────┘");
        }
    }

    private String padRight(String s, int width) {
        if (s.length() >= width) {
            return s.substring(0, width - 3) + "...";
        }
        return String.format("%-" + width + "s", s);
    }
}
